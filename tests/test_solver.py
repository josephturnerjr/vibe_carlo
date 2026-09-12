"""Tests for the safe-spending solver.

The solver's whole claim is that it inverts the engines exactly, so most of
these tests are round-trips: solve for a success rate, feed the answer back
through the engine, and check the engine agrees.
"""

import numpy as np
import pytest

from vibe_carlo.schemas import (
    FlatDistribution,
    PlanParameterSet,
    SimulationInput,
    SpendingDistribution,
    TruncatedNormalDistribution,
    UniformDistribution,
)
from vibe_carlo.simulation import solver
from vibe_carlo.simulation.engine import run_simulation
from vibe_carlo.simulation.models import load_historical_data
from vibe_carlo.simulation.plan_engine import run_plan_simulation
from vibe_carlo.simulation.solver import (
    SUCCESS_LEVELS,
    solve_plan_safe_spending,
    solve_safe_spending,
)

N_RUNS = 5_000
SEED = 3
# The engine's success rate moves in steps of 1/N_RUNS, so an exact inversion
# still lands a fraction of a percentage point away from the requested level.
TOLERANCE_PP = 0.2


@pytest.fixture(scope="module")
def historical() -> np.ndarray:
    return load_historical_data()


def scale(dist: SpendingDistribution, m: float) -> SpendingDistribution:
    """Scale a distribution the same way the solver's multiplier does."""
    if isinstance(dist, FlatDistribution):
        return FlatDistribution(value=dist.value * m)
    if isinstance(dist, UniformDistribution):
        return UniformDistribution(low=dist.low * m, high=dist.high * m)
    return TruncatedNormalDistribution(
        low=dist.low * m, high=dist.high * m, mean=dist.mean * m, stddev=dist.stddev * m
    )


def make_input(
    spending: SpendingDistribution,
    earnings: float = 0.0,
    tax: float = 0.0,
    years: int = 30,
) -> SimulationInput:
    return SimulationInput(
        cash_value=50_000.0,
        market_value=800_000.0,
        bond_value=150_000.0,
        earnings=earnings,
        spending_distribution=spending,
        years_to_simulate=years,
        sample_years=5,
        withdrawal_tax_rate=tax,
    )


def engine_rate(
    params: SimulationInput,
    historical: np.ndarray,
    multiplier: float,
    target: float = 0.0,
) -> float:
    """Success rate the engine reports at a solved multiplier, as a percentage."""
    scaled = params.model_copy(
        update={"spending_distribution": scale(params.spending_distribution, multiplier)}
    )
    result = run_simulation(scaled, historical, n_runs=N_RUNS, seed=SEED)
    if target > 0:
        final = np.array(result.final_year_distribution)
        return 100.0 * float(np.mean(final >= target))
    return 100.0 * result.success_rate


# ---------------------------------------------------------------------------
# Round-trips against the single-parameter-set engine
# ---------------------------------------------------------------------------


def test_flat_spending_round_trips(historical: np.ndarray) -> None:
    params = make_input(FlatDistribution(value=40_000))
    table = solve_safe_spending(params, historical, n_runs=N_RUNS, seed=SEED)

    assert table.method == "closed_form"
    for row in table.rows:
        assert row.multiplier is not None
        got = engine_rate(params, historical, row.multiplier)
        assert abs(got - row.success_pct) < TOLERANCE_PP


def test_uniform_spending_with_tax_round_trips(historical: np.ndarray) -> None:
    params = make_input(UniformDistribution(low=30_000, high=50_000), tax=0.2)
    table = solve_safe_spending(params, historical, n_runs=N_RUNS, seed=SEED)

    for row in table.rows:
        assert row.multiplier is not None
        got = engine_rate(params, historical, row.multiplier)
        assert abs(got - row.success_pct) < TOLERANCE_PP


def test_truncated_normal_spending_round_trips(historical: np.ndarray) -> None:
    params = make_input(
        TruncatedNormalDistribution(low=30_000, high=60_000, mean=45_000, stddev=5_000)
    )
    table = solve_safe_spending(params, historical, n_runs=N_RUNS, seed=SEED)

    for row in table.rows:
        assert row.multiplier is not None
        got = engine_rate(params, historical, row.multiplier)
        assert abs(got - row.success_pct) < TOLERANCE_PP


def test_terminal_target_round_trips(historical: np.ndarray) -> None:
    params = make_input(FlatDistribution(value=40_000))
    target = 500_000.0
    table = solve_safe_spending(
        params, historical, target_net_worth=target, n_runs=N_RUNS, seed=SEED
    )

    assert table.target_net_worth == target
    # A demanding target can put the worst sampled path out of reach at any
    # spending level, which is a legitimate None — but only at the top of the
    # table, since a lower success rate is never harder to hit.
    checked = 0
    for row in table.rows:
        if row.multiplier is None:
            assert row.success_pct == 100, f"{row.success_pct}% unexpectedly unreachable"
            continue
        got = engine_rate(params, historical, row.multiplier, target=target)
        assert abs(got - row.success_pct) < TOLERANCE_PP
        checked += 1
    assert checked >= len(SUCCESS_LEVELS) - 1


def test_terminal_target_lowers_safe_spending(historical: np.ndarray) -> None:
    params = make_input(FlatDistribution(value=40_000))
    without = solve_safe_spending(params, historical, n_runs=N_RUNS, seed=SEED)
    with_target = solve_safe_spending(
        params, historical, target_net_worth=500_000.0, n_runs=N_RUNS, seed=SEED
    )

    compared = 0
    for lhs, rhs in zip(without.rows, with_target.rows):
        assert lhs.annual_spending is not None
        if rhs.annual_spending is None:
            # Requiring a balance at the end made this row unreachable, which is
            # the strongest form of "lower".
            continue
        assert rhs.annual_spending < lhs.annual_spending
        compared += 1
    assert compared >= len(SUCCESS_LEVELS) - 1


# ---------------------------------------------------------------------------
# The refinement path, where earnings break the closed form's linearity
# ---------------------------------------------------------------------------


def test_surplus_years_trigger_refinement(historical: np.ndarray) -> None:
    # Earnings sit inside the spending range, so some years are covered by
    # earnings alone and the closed form's "every year withdraws" assumption
    # no longer holds. The tax rate matters: it is the gross-up that the linear
    # model misapplies to a surplus.
    params = make_input(UniformDistribution(low=30_000, high=90_000), earnings=60_000.0, tax=0.25)
    table = solve_safe_spending(params, historical, n_runs=N_RUNS, seed=SEED)

    assert table.method == "refined"
    for row in table.rows:
        assert row.multiplier is not None
        got = engine_rate(params, historical, row.multiplier)
        assert abs(got - row.success_pct) < TOLERANCE_PP


def _skip_refinement(seed_multipliers: np.ndarray, **kwargs: object) -> np.ndarray:
    """Stand-in for the refinement pass that hands back the closed form untouched."""
    return seed_multipliers


def test_closed_form_alone_would_be_optimistic(
    historical: np.ndarray, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guards the reason refinement exists, not just that it runs.

    Grossing up a surplus as if it were a tax refund over-credits it, so the
    unrefined answer allows more spending than the engine actually supports.
    """
    params = make_input(UniformDistribution(low=30_000, high=90_000), earnings=60_000.0, tax=0.25)
    refined = solve_safe_spending(params, historical, n_runs=N_RUNS, seed=SEED)

    monkeypatch.setattr(solver, "_refine_multipliers", _skip_refinement)
    unrefined = solve_safe_spending(params, historical, n_runs=N_RUNS, seed=SEED)

    row = next(r for r in unrefined.rows if r.success_pct == 90)
    assert row.multiplier is not None
    overstated = engine_rate(params, historical, row.multiplier)
    assert overstated < 90 - TOLERANCE_PP

    refined_row = next(r for r in refined.rows if r.success_pct == 90)
    assert refined_row.annual_spending is not None
    assert row.annual_spending is not None
    assert refined_row.annual_spending < row.annual_spending


# ---------------------------------------------------------------------------
# Table shape and invariants
# ---------------------------------------------------------------------------


def test_table_covers_every_success_level(historical: np.ndarray) -> None:
    table = solve_safe_spending(
        make_input(FlatDistribution(value=40_000)), historical, n_runs=N_RUNS, seed=SEED
    )
    assert [row.success_pct for row in table.rows] == list(SUCCESS_LEVELS)


def test_success_levels_are_five_percent_increments() -> None:
    steps = {a - b for a, b in zip(SUCCESS_LEVELS, SUCCESS_LEVELS[1:])}
    assert steps == {5}


def test_table_starts_at_one_hundred_percent() -> None:
    assert SUCCESS_LEVELS[0] == 100


def test_hundred_percent_row_never_exceeds_ninety_five(historical: np.ndarray) -> None:
    """The worst sampled path cannot support more than the 5th-percentile one."""
    for params in (
        make_input(FlatDistribution(value=40_000)),
        make_input(UniformDistribution(low=30_000, high=50_000), tax=0.2),
        make_input(UniformDistribution(low=30_000, high=90_000), earnings=60_000.0, tax=0.25),
    ):
        table = solve_safe_spending(params, historical, n_runs=N_RUNS, seed=SEED)
        rows = {row.success_pct: row.annual_spending for row in table.rows}
        assert rows[100] is not None
        assert rows[95] is not None
        assert rows[100] <= rows[95]


def test_hundred_percent_row_round_trips(historical: np.ndarray) -> None:
    """Spending the 100% figure must leave every simulated run solvent."""
    params = make_input(FlatDistribution(value=40_000))
    table = solve_safe_spending(params, historical, n_runs=N_RUNS, seed=SEED)

    row = next(r for r in table.rows if r.success_pct == 100)
    assert row.multiplier is not None
    got = engine_rate(params, historical, row.multiplier)
    assert abs(got - 100) < TOLERANCE_PP


def test_higher_success_demands_lower_spending(historical: np.ndarray) -> None:
    table = solve_safe_spending(
        make_input(FlatDistribution(value=40_000)), historical, n_runs=N_RUNS, seed=SEED
    )
    spends = [row.annual_spending for row in table.rows]
    assert all(s is not None for s in spends)
    # SUCCESS_LEVELS descends, so spending must ascend.
    assert spends == sorted(spends)  # type: ignore[type-var]


def test_reports_current_mean_spending(historical: np.ndarray) -> None:
    params = make_input(FlatDistribution(value=40_000))
    table = solve_safe_spending(params, historical, n_runs=N_RUNS, seed=SEED)

    assert table.current_mean_spending == pytest.approx(40_000)
    assert table.solve_years == 30
    assert table.phase_name is None
    # Multiplier and dollars describe the same answer.
    for row in table.rows:
        assert row.multiplier is not None
        assert row.annual_spending == pytest.approx(row.multiplier * 40_000)


def test_unreachable_target_reports_none(historical: np.ndarray) -> None:
    # A terminal target far above what the portfolio could ever reach.
    params = make_input(FlatDistribution(value=40_000))
    table = solve_safe_spending(
        params, historical, target_net_worth=500_000_000.0, n_runs=N_RUNS, seed=SEED
    )
    assert all(row.annual_spending is None for row in table.rows)
    assert all(row.multiplier is None for row in table.rows)


# ---------------------------------------------------------------------------
# Plans: only the final phase is solved
# ---------------------------------------------------------------------------


def param_set(
    name: str,
    order: int,
    duration: int | None,
    spending: SpendingDistribution,
    earnings: float = 0.0,
    tax: float = 0.0,
) -> PlanParameterSet:
    return PlanParameterSet(
        id=order + 1,
        plan_id=1,
        name=name,
        order_position=order,
        duration=duration,
        cash_value=50_000.0,
        market_value=800_000.0,
        bond_value=150_000.0,
        earnings=earnings,
        spending_distribution=spending,
        withdrawal_tax_rate=tax,
    )


@pytest.fixture
def plan_phases() -> list[PlanParameterSet]:
    return [
        param_set("working", 0, 10, FlatDistribution(value=90_000), earnings=150_000.0),
        param_set("bridge", 1, 5, FlatDistribution(value=80_000), earnings=30_000.0, tax=0.1),
        param_set(
            "retirement",
            2,
            None,
            UniformDistribution(low=50_000, high=70_000),
            earnings=25_000.0,
            tax=0.18,
        ),
    ]


def plan_engine_rate(
    phases: list[PlanParameterSet],
    historical: np.ndarray,
    multiplier: float,
    years: int = 35,
    target: float = 0.0,
) -> float:
    scaled = phases[:-1] + [
        phases[-1].model_copy(
            update={"spending_distribution": scale(phases[-1].spending_distribution, multiplier)}
        )
    ]
    result = run_plan_simulation(scaled, years, 5, historical, n_runs=N_RUNS, seed=SEED)
    if target > 0:
        final = np.array(result.final_year_distribution)
        return 100.0 * float(np.mean(final >= target))
    return 100.0 * result.success_rate


def test_plan_last_phase_round_trips(
    plan_phases: list[PlanParameterSet], historical: np.ndarray
) -> None:
    table = solve_plan_safe_spending(plan_phases, 35, 5, historical, n_runs=N_RUNS, seed=SEED)

    assert table.phase_name == "retirement"
    assert table.solve_years == 20  # 35 total less the 10 + 5 committed years
    for row in table.rows:
        assert row.multiplier is not None
        got = plan_engine_rate(plan_phases, historical, row.multiplier)
        assert abs(got - row.success_pct) < TOLERANCE_PP


def test_plan_terminal_target_round_trips(
    plan_phases: list[PlanParameterSet], historical: np.ndarray
) -> None:
    target = 400_000.0
    table = solve_plan_safe_spending(
        plan_phases, 35, 5, historical, target_net_worth=target, n_runs=N_RUNS, seed=SEED
    )
    for row in table.rows:
        assert row.multiplier is not None
        got = plan_engine_rate(plan_phases, historical, row.multiplier, target=target)
        assert abs(got - row.success_pct) < TOLERANCE_PP


def test_plan_earlier_phases_are_untouched(
    plan_phases: list[PlanParameterSet], historical: np.ndarray
) -> None:
    """Changing a committed phase must move the answer; the solver never edits it."""
    before = solve_plan_safe_spending(plan_phases, 35, 5, historical, n_runs=N_RUNS, seed=SEED)

    thriftier = list(plan_phases)
    thriftier[0] = thriftier[0].model_copy(
        update={"spending_distribution": FlatDistribution(value=60_000)}
    )
    after = solve_plan_safe_spending(thriftier, 35, 5, historical, n_runs=N_RUNS, seed=SEED)

    # Spending less while working leaves more for retirement.
    for lhs, rhs in zip(before.rows, after.rows):
        assert lhs.annual_spending is not None
        assert rhs.annual_spending is not None
        assert rhs.annual_spending > lhs.annual_spending

    # The inputs themselves are untouched.
    assert plan_phases[0].spending_distribution.value == 90_000  # type: ignore[union-attr]


def test_plan_reports_last_phase_mean_spending(
    plan_phases: list[PlanParameterSet], historical: np.ndarray
) -> None:
    table = solve_plan_safe_spending(plan_phases, 35, 5, historical, n_runs=N_RUNS, seed=SEED)
    # Mean of Uniform(50k, 70k), sampled.
    assert table.current_mean_spending == pytest.approx(60_000, rel=0.02)


def test_plan_single_phase_solves_whole_horizon(historical: np.ndarray) -> None:
    phases = [param_set("all of it", 0, None, FlatDistribution(value=40_000))]
    table = solve_plan_safe_spending(phases, 30, 5, historical, n_runs=N_RUNS, seed=SEED)

    assert table.phase_name == "all of it"
    assert table.solve_years == 30


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_rejects_zero_spending_to_solve_for(historical: np.ndarray) -> None:
    params = make_input(FlatDistribution(value=0.0))
    with pytest.raises(ValueError, match="spending being solved for is zero"):
        solve_safe_spending(params, historical, n_runs=100, seed=SEED)


def test_rejects_negative_target(historical: np.ndarray) -> None:
    params = make_input(FlatDistribution(value=40_000))
    with pytest.raises(ValueError, match="non-negative"):
        solve_safe_spending(params, historical, target_net_worth=-1.0, n_runs=100, seed=SEED)


def test_rejects_empty_plan(historical: np.ndarray) -> None:
    with pytest.raises(ValueError, match="At least one parameter set"):
        solve_plan_safe_spending([], 30, 5, historical, n_runs=100, seed=SEED)


def test_surplus_without_tax_stays_closed_form(historical: np.ndarray) -> None:
    """A surplus year with no gross-up does not break linearity, so no refining."""
    params = make_input(UniformDistribution(low=30_000, high=90_000), earnings=60_000.0)
    table = solve_safe_spending(params, historical, n_runs=N_RUNS, seed=SEED)

    assert table.method == "closed_form"
    for row in table.rows:
        assert row.multiplier is not None
        got = engine_rate(params, historical, row.multiplier)
        assert abs(got - row.success_pct) < TOLERANCE_PP
