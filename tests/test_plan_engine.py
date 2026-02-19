"""Unit tests for the plan simulation engine."""

import numpy as np
import pytest

from vibe_carlo.schemas import (
    FilingStatus,
    FlatDistribution,
    PlanParameterSet,
    UniformDistribution,
)
from vibe_carlo.simulation.engine import run_simulation
from vibe_carlo.simulation.models import load_historical_data
from vibe_carlo.simulation.plan_engine import run_plan_simulation


def _make_ps(
    ps_id: int = 1,
    plan_id: int = 1,
    name: str = "Phase",
    order_position: int = 0,
    duration: int | None = None,
    cash: float = 10_000.0,
    market: float = 70_000.0,
    bonds: float = 20_000.0,
    earnings: float = 12_000.0,
    spending: FlatDistribution | UniformDistribution | None = None,
    filing_status: FilingStatus | None = None,
) -> PlanParameterSet:
    dist = spending or FlatDistribution(value=0.0)
    return PlanParameterSet(
        id=ps_id,
        plan_id=plan_id,
        name=name,
        order_position=order_position,
        duration=duration,
        cash_value=cash,
        market_value=market,
        bond_value=bonds,
        earnings=earnings,
        spending_distribution=dist,
        filing_status=filing_status,
    )


# --- Critical: single-phase equivalence ---


def test_single_phase_matches_regular_simulation() -> None:
    """Plan with 1 parameter set must produce identical results to run_simulation."""
    from vibe_carlo.schemas import SimulationInput

    data = load_historical_data()
    ps = _make_ps()

    sim_input = SimulationInput(
        cash_value=ps.cash_value,
        market_value=ps.market_value,
        bond_value=ps.bond_value,
        earnings=ps.earnings,
        spending_distribution=ps.spending_distribution,
        years_to_simulate=30,
        sample_years=30,
    )

    result_regular = run_simulation(sim_input, data, n_runs=1000, seed=42)
    result_plan = run_plan_simulation(
        [ps],
        years_to_simulate=30,
        sample_years=30,
        historical_data=data,
        n_runs=1000,
        seed=42,
    )

    assert result_plan.success_rate == result_regular.success_rate
    assert result_plan.year_labels == result_regular.year_labels
    for key in ("p10", "p25", "p50", "p75", "p90"):
        np.testing.assert_allclose(
            result_plan.percentiles[key],
            result_regular.percentiles[key],
            rtol=1e-10,
        )


# --- Happy path ---


def test_two_phase_output_shape() -> None:
    data = load_historical_data()
    ps1 = _make_ps(ps_id=1, name="Working", order_position=0, duration=10)
    ps2 = _make_ps(ps_id=2, name="Retired", order_position=1)

    result = run_plan_simulation(
        [ps1, ps2],
        years_to_simulate=30,
        sample_years=30,
        historical_data=data,
        n_runs=100,
        seed=42,
    )

    assert len(result.year_labels) == 31
    for key in ("p10", "p25", "p50", "p75", "p90"):
        assert len(result.percentiles[key]) == 31
    assert len(result.final_year_distribution) == 100


def test_three_phases() -> None:
    data = load_historical_data()
    ps1 = _make_ps(ps_id=1, name="Working", order_position=0, duration=5, earnings=50000)
    ps2 = _make_ps(ps_id=2, name="Semi-retired", order_position=1, duration=10, earnings=25000)
    ps3 = _make_ps(ps_id=3, name="Retired", order_position=2, earnings=0)

    result = run_plan_simulation(
        [ps1, ps2, ps3],
        years_to_simulate=30,
        sample_years=30,
        historical_data=data,
        n_runs=100,
        seed=42,
    )

    assert len(result.year_labels) == 31
    assert 0.0 <= result.success_rate <= 1.0


def test_deterministic_with_seed() -> None:
    data = load_historical_data()
    ps = _make_ps()

    r1 = run_plan_simulation(
        [ps],
        years_to_simulate=20,
        sample_years=20,
        historical_data=data,
        n_runs=100,
        seed=123,
    )
    r2 = run_plan_simulation(
        [ps],
        years_to_simulate=20,
        sample_years=20,
        historical_data=data,
        n_runs=100,
        seed=123,
    )

    assert r1.success_rate == r2.success_rate
    assert r1.percentiles == r2.percentiles


def test_success_rate_bounds() -> None:
    data = load_historical_data()
    ps = _make_ps()

    result = run_plan_simulation(
        [ps],
        years_to_simulate=30,
        sample_years=30,
        historical_data=data,
        n_runs=1000,
        seed=42,
    )
    assert 0.0 <= result.success_rate <= 1.0


def test_percentile_ordering() -> None:
    data = load_historical_data()
    ps = _make_ps()

    result = run_plan_simulation(
        [ps],
        years_to_simulate=30,
        sample_years=30,
        historical_data=data,
        n_runs=1000,
        seed=42,
    )

    for i in range(len(result.year_labels)):
        assert result.percentiles["p10"][i] <= result.percentiles["p25"][i]
        assert result.percentiles["p25"][i] <= result.percentiles["p50"][i]
        assert result.percentiles["p50"][i] <= result.percentiles["p75"][i]
        assert result.percentiles["p75"][i] <= result.percentiles["p90"][i]


# --- Behavioral ---


def test_spending_changes_between_phases() -> None:
    """Higher Phase 2 spending should lower success rate compared to low Phase 2 spending."""
    data = load_historical_data()
    ps1 = _make_ps(
        ps_id=1,
        order_position=0,
        duration=10,
        spending=FlatDistribution(value=5000),
        earnings=0,
    )
    # Low Phase 2 spending
    ps2_low = _make_ps(
        ps_id=2,
        order_position=1,
        spending=FlatDistribution(value=5000),
        earnings=0,
    )
    # High Phase 2 spending
    ps2_high = _make_ps(
        ps_id=2,
        order_position=1,
        spending=FlatDistribution(value=30000),
        earnings=0,
    )

    r_low = run_plan_simulation(
        [ps1, ps2_low],
        years_to_simulate=30,
        sample_years=30,
        historical_data=data,
        n_runs=1000,
        seed=42,
    )
    r_high = run_plan_simulation(
        [ps1, ps2_high],
        years_to_simulate=30,
        sample_years=30,
        historical_data=data,
        n_runs=1000,
        seed=42,
    )

    assert r_high.success_rate < r_low.success_rate


def test_earnings_changes_between_phases() -> None:
    """Losing earnings in Phase 2 should lower success rate."""
    data = load_historical_data()
    spending = FlatDistribution(value=20000)
    ps1 = _make_ps(
        ps_id=1,
        order_position=0,
        duration=10,
        spending=spending,
        earnings=25000,
    )
    ps2_with = _make_ps(
        ps_id=2,
        order_position=1,
        spending=spending,
        earnings=25000,
    )
    ps2_without = _make_ps(
        ps_id=2,
        order_position=1,
        spending=spending,
        earnings=0,
    )

    r_with = run_plan_simulation(
        [ps1, ps2_with],
        years_to_simulate=30,
        sample_years=30,
        historical_data=data,
        n_runs=1000,
        seed=42,
    )
    r_without = run_plan_simulation(
        [ps1, ps2_without],
        years_to_simulate=30,
        sample_years=30,
        historical_data=data,
        n_runs=1000,
        seed=42,
    )

    assert r_without.success_rate < r_with.success_rate


def test_portfolio_carries_over() -> None:
    """Phase 2 does NOT reset portfolio - it carries over from Phase 1."""
    data = load_historical_data()
    # Phase 1: zero spending, earnings surplus → portfolio grows
    ps1 = _make_ps(
        ps_id=1,
        order_position=0,
        duration=10,
        spending=FlatDistribution(value=0),
        earnings=10000,
    )
    # Phase 2: moderate spending
    ps2 = _make_ps(
        ps_id=2,
        order_position=1,
        spending=FlatDistribution(value=5000),
        earnings=0,
    )

    result = run_plan_simulation(
        [ps1, ps2],
        years_to_simulate=20,
        sample_years=20,
        historical_data=data,
        n_runs=100,
        seed=42,
    )

    # Portfolio at year 10 should be higher than initial (grew during Phase 1)
    total_initial = ps1.cash_value + ps1.market_value + ps1.bond_value
    assert result.percentiles["p50"][10] > total_initial


def test_tax_differs_per_phase() -> None:
    """Phase 1 no tax, Phase 2 with tax should differ from both phases no tax."""
    data = load_historical_data()
    spending = FlatDistribution(value=30000)
    ps1 = _make_ps(
        ps_id=1,
        order_position=0,
        duration=10,
        cash=50_000,
        market=400_000,
        bonds=50_000,
        spending=spending,
        earnings=0,
        filing_status=None,
    )
    ps2_no_tax = _make_ps(
        ps_id=2,
        order_position=1,
        cash=50_000,
        market=400_000,
        bonds=50_000,
        spending=spending,
        earnings=0,
        filing_status=None,
    )
    ps2_tax = _make_ps(
        ps_id=2,
        order_position=1,
        cash=50_000,
        market=400_000,
        bonds=50_000,
        spending=spending,
        earnings=0,
        filing_status=FilingStatus.single,
    )

    r_no = run_plan_simulation(
        [ps1, ps2_no_tax],
        years_to_simulate=30,
        sample_years=30,
        historical_data=data,
        n_runs=1000,
        seed=42,
    )
    r_tax = run_plan_simulation(
        [ps1, ps2_tax],
        years_to_simulate=30,
        sample_years=30,
        historical_data=data,
        n_runs=1000,
        seed=42,
    )

    # Tax in Phase 2 should lower success rate
    assert r_tax.success_rate < r_no.success_rate


# --- Edge cases ---


def test_sim_shorter_than_plan_durations() -> None:
    """4yr sim with phases [3yr, 5yr, remainder] uses only 2 phases."""
    data = load_historical_data()
    ps1 = _make_ps(ps_id=1, order_position=0, duration=3)
    ps2 = _make_ps(ps_id=2, order_position=1, duration=5)
    ps3 = _make_ps(ps_id=3, order_position=2)

    result = run_plan_simulation(
        [ps1, ps2, ps3],
        years_to_simulate=4,
        sample_years=4,
        historical_data=data,
        n_runs=100,
        seed=42,
    )

    assert len(result.year_labels) == 5  # 0..4


def test_sim_equal_to_explicit_durations() -> None:
    """8yr sim with phases [3yr, 5yr, remainder] uses exactly [3yr, 5yr]."""
    data = load_historical_data()
    ps1 = _make_ps(ps_id=1, order_position=0, duration=3)
    ps2 = _make_ps(ps_id=2, order_position=1, duration=5)
    ps3 = _make_ps(ps_id=3, order_position=2)

    result = run_plan_simulation(
        [ps1, ps2, ps3],
        years_to_simulate=8,
        sample_years=8,
        historical_data=data,
        n_runs=100,
        seed=42,
    )

    assert len(result.year_labels) == 9  # 0..8


def test_empty_parameter_sets_error() -> None:
    data = load_historical_data()
    with pytest.raises(ValueError, match="At least one parameter set"):
        run_plan_simulation(
            [],
            years_to_simulate=30,
            sample_years=30,
            historical_data=data,
        )


def test_single_year_phases() -> None:
    """Each phase is 1 year."""
    data = load_historical_data()
    phases = [
        _make_ps(ps_id=i + 1, order_position=i, duration=1 if i < 4 else None) for i in range(5)
    ]

    result = run_plan_simulation(
        phases,
        years_to_simulate=5,
        sample_years=5,
        historical_data=data,
        n_runs=100,
        seed=42,
    )

    assert len(result.year_labels) == 6


def test_last_set_duration_ignored() -> None:
    """Last set's duration field doesn't affect simulation (uses remainder)."""
    data = load_historical_data()
    ps1 = _make_ps(ps_id=1, order_position=0, duration=10)
    ps2_with_dur = _make_ps(ps_id=2, order_position=1, duration=5)
    ps2_no_dur = _make_ps(ps_id=2, order_position=1, duration=None)

    r1 = run_plan_simulation(
        [ps1, ps2_with_dur],
        years_to_simulate=30,
        sample_years=30,
        historical_data=data,
        n_runs=100,
        seed=42,
    )
    r2 = run_plan_simulation(
        [ps1, ps2_no_dur],
        years_to_simulate=30,
        sample_years=30,
        historical_data=data,
        n_runs=100,
        seed=42,
    )

    assert r1.success_rate == r2.success_rate
    assert r1.percentiles == r2.percentiles


def test_single_param_set_plan() -> None:
    """Plan with exactly 1 parameter set (no duration needed)."""
    data = load_historical_data()
    ps = _make_ps(duration=None)

    result = run_plan_simulation(
        [ps],
        years_to_simulate=10,
        sample_years=10,
        historical_data=data,
        n_runs=100,
        seed=42,
    )

    assert len(result.year_labels) == 11
    assert 0.0 <= result.success_rate <= 1.0
