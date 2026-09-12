"""Solve for the spending level that achieves a target success rate.

The engines answer "given this spending, what fraction of runs survive?". This
module answers the inverse: "given a target success rate, how much can be
spent?" — and it answers it for every success rate at once.

The trick is that within a single run the portfolio recursion is *linear* in
the spending level, so each run has an exact critical spending multiplier: the
largest multiple of the authored spending that run could have sustained. Ruin
for a run is then simply ``m > m*``, so the success rate at multiplier ``m`` is
the fraction of runs with ``m* >= m``, and the answer at any success rate is a
quantile of the ``m*`` distribution. One simulation pass yields the whole table
with no search.

Linearity holds only while every year in the solve window is a withdrawal year
(spending above earnings). When earnings exceed spending in some year, the
``max(spending - earnings, 0)`` clamp introduces a kink and the closed form
becomes optimistic. That case is detected and refined by a vectorised bisection
against the exact clamped recursion, which is monotone in ``m`` and so always
converges.
"""

import numpy as np
import numpy.typing as npt

from vibe_carlo.schemas import (
    PlanParameterSet,
    SafeSpendingRow,
    SafeSpendingTable,
    SimulationInput,
)
from vibe_carlo.simulation.distributions import sample_spending
from vibe_carlo.simulation.engine import _build_bootstrap_indices
from vibe_carlo.simulation.models import COL_BOND, COL_CPI, COL_SP500
from vibe_carlo.simulation.plan_engine import compute_phase_durations

# Success rates shown in the table, in 5% increments. Deliberately stops at 95%:
# the historical dataset is only ~100 rows, so the far tail is limited by the
# data rather than by the number of Monte Carlo runs, and a 99% row would imply
# a precision the model does not have.
SUCCESS_LEVELS: tuple[int, ...] = (95, 90, 85, 80, 75, 70, 65, 60, 55, 50)

# Bisection settings for the refinement path.
_REFINE_ITERATIONS = 60
_BRACKET_EXPANSIONS = 20


def _real_returns(
    rng: np.random.Generator,
    historical_data: npt.NDArray[np.float64],
    n_runs: int,
    years: int,
    block_len: int,
    market_alloc: float,
    bond_alloc: float,
) -> npt.NDArray[np.float64]:
    """Sample block-bootstrapped real returns, shape (n_runs, years)."""
    indices = _build_bootstrap_indices(rng, n_runs, years, block_len, len(historical_data))
    sampled = historical_data[indices]
    nominal = market_alloc * sampled[:, :, COL_SP500] + bond_alloc * sampled[:, :, COL_BOND]
    return (1 + nominal) / (1 + sampled[:, :, COL_CPI]) - 1


def _net_flow(
    spending: npt.NDArray[np.float64],
    earnings: npt.NDArray[np.float64],
    tax_divisor: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Exact net portfolio outflow, matching the engines' clamped arithmetic."""
    shortfall = np.maximum(spending - earnings, 0.0)
    surplus = np.maximum(earnings - spending, 0.0)
    return shortfall * tax_divisor - surplus


def _closed_form_multipliers(
    real_returns: npt.NDArray[np.float64],
    const_flow: npt.NDArray[np.float64],
    linear_flow: npt.NDArray[np.float64],
    initial_portfolio: float,
    target_net_worth: float,
) -> npt.NDArray[np.float64]:
    """Per-run critical multiplier, assuming every solve-window year withdraws.

    Year ``k``'s net outflow is modelled as ``const_flow[k] + m * linear_flow[k]``.
    Unrolling the recursion, the portfolio after ``n`` years is
    ``A_n * (P0 - G_n)`` where ``A_n`` is cumulative growth and ``G_n`` is the
    discounted sum of flows, so survival through every year plus a terminal
    balance of at least ``target_net_worth`` reduces to a set of linear bounds
    on ``m``. Runs that fail at any non-negative ``m`` come back as ``-inf``.
    """
    growth = np.cumprod(1.0 + real_returns, axis=1)
    discount = 1.0 / growth
    final_growth = growth[:, -1]

    # G_n = const_part + m * linear_part, for n = 1..N along axis 1.
    const_part = np.cumsum(const_flow * discount, axis=1)
    linear_part = np.cumsum(linear_flow * discount, axis=1)

    # Survival through year n needs G_n < P0.
    headroom = initial_portfolio - const_part
    with np.errstate(divide="ignore", invalid="ignore"):
        ruin_bounds = np.where(linear_part > 0, headroom / linear_part, np.inf)
    critical = np.min(ruin_bounds, axis=1)

    # A year whose bound does not depend on m still fails if it is already under water.
    fails_regardless = np.any((linear_part <= 0) & (headroom <= 0), axis=1)

    # Terminal balance needs G_N <= P0 - target / A_N.
    terminal_headroom = headroom[:, -1] - target_net_worth / final_growth
    terminal_linear = linear_part[:, -1]
    with np.errstate(divide="ignore", invalid="ignore"):
        terminal_bound = np.where(terminal_linear > 0, terminal_headroom / terminal_linear, np.inf)
    critical = np.minimum(critical, terminal_bound)
    fails_regardless |= (terminal_linear <= 0) & (terminal_headroom < 0)

    return np.where(fails_regardless | (critical <= 0), -np.inf, critical)


def _survives(
    multiplier: npt.NDArray[np.float64],
    real_returns: npt.NDArray[np.float64],
    fixed_flow: npt.NDArray[np.float64],
    basis: npt.NDArray[np.float64],
    earnings: npt.NDArray[np.float64],
    tax_divisor: npt.NDArray[np.float64],
    window: slice,
    initial_portfolio: float,
    target_net_worth: float,
) -> npt.NDArray[np.bool_]:
    """Exact clamped simulation at a per-run multiplier. Mirrors the engines."""
    flow = fixed_flow.copy()
    spending = multiplier[:, None] * basis[:, window]
    flow[:, window] = _net_flow(spending, earnings[:, window], tax_divisor[:, window])

    n_runs, years = real_returns.shape
    value = np.full(n_runs, initial_portfolio, dtype=np.float64)
    alive = np.ones(n_runs, dtype=bool)
    for y in range(years):
        value = value * (1 + real_returns[:, y]) - flow[:, y]
        value = np.maximum(value, 0.0)
        alive &= value > 0.0
    return alive & (value >= target_net_worth)


def _refine_multipliers(
    seed_multipliers: npt.NDArray[np.float64],
    **kwargs: object,
) -> npt.NDArray[np.float64]:
    """Vectorised per-run bisection against the exact recursion.

    ``_survives`` is monotone decreasing in the multiplier, so each run's
    critical value is bracketed and bisected independently but in lockstep, at
    the cost of one clamped simulation pass per iteration.
    """
    finite = np.isfinite(seed_multipliers)
    low = np.zeros_like(seed_multipliers)
    high = np.where(finite, np.maximum(seed_multipliers, 1e-9), 1e-9)

    def survives(m: npt.NDArray[np.float64]) -> npt.NDArray[np.bool_]:
        return _survives(m, **kwargs)  # type: ignore[arg-type]

    # The closed form is optimistic, so `high` normally already fails. Expand
    # anyway for the rare run where it does not.
    for _ in range(_BRACKET_EXPANSIONS):
        still_alive = survives(high)
        if not np.any(still_alive):
            break
        high = np.where(still_alive, high * 2.0, high)

    # A run that cannot even sustain zero spending is unachievable outright.
    unachievable = ~survives(low)

    for _ in range(_REFINE_ITERATIONS):
        mid = 0.5 * (low + high)
        ok = survives(mid)
        low = np.where(ok, mid, low)
        high = np.where(ok, high, mid)

    return np.where(unachievable, -np.inf, low)


def _build_table(
    critical: npt.NDArray[np.float64],
    basis_mean: float,
    target_net_worth: float,
    solve_years: int,
    phase_name: str | None,
    refined: bool,
) -> SafeSpendingTable:
    rows: list[SafeSpendingRow] = []
    for level in SUCCESS_LEVELS:
        # Runs that fail at any spending level carry -inf; interpolating between
        # two of those is inf - inf, which is exactly the "unreachable" answer
        # but arrives as a nan. Both are caught by the finiteness check below.
        with np.errstate(invalid="ignore"):
            value = float(np.quantile(critical, 1.0 - level / 100.0))
        if np.isfinite(value) and value > 0:
            rows.append(
                SafeSpendingRow(
                    success_pct=level,
                    multiplier=value,
                    annual_spending=value * basis_mean,
                )
            )
        else:
            rows.append(SafeSpendingRow(success_pct=level, multiplier=None, annual_spending=None))

    return SafeSpendingTable(
        rows=rows,
        target_net_worth=target_net_worth,
        current_mean_spending=basis_mean,
        solve_years=solve_years,
        phase_name=phase_name,
        method="refined" if refined else "closed_form",
    )


def _solve(
    real_returns: npt.NDArray[np.float64],
    basis: npt.NDArray[np.float64],
    earnings: npt.NDArray[np.float64],
    tax_divisor: npt.NDArray[np.float64],
    window: slice,
    initial_portfolio: float,
    target_net_worth: float,
    phase_name: str | None,
) -> SafeSpendingTable:
    """Shared solve: window years scale with the multiplier, the rest are fixed."""
    basis_mean = float(np.mean(basis[:, window]))
    if basis_mean <= 0:
        raise ValueError(
            "Cannot solve for safe spending when the spending being solved for is zero"
        )

    # Years outside the window keep their exact flow; years inside are linear in m.
    fixed_flow = _net_flow(basis, earnings, tax_divisor)
    fixed_flow[:, window] = 0.0

    const_flow = fixed_flow.copy()
    const_flow[:, window] = -earnings[:, window] * tax_divisor[:, window]
    linear_flow = np.zeros_like(basis)
    linear_flow[:, window] = basis[:, window] * tax_divisor[:, window]

    critical = _closed_form_multipliers(
        real_returns, const_flow, linear_flow, initial_portfolio, target_net_worth
    )

    # The closed form assumed every window year is a withdrawal year. Check that
    # against the answer it produced. A surplus year only breaks the model when
    # a gross-up applies to it: at a zero tax rate the divisor is 1, so
    # `shortfall * 1 - surplus` already equals the linear `(spending - earnings)`
    # and the closed form stays exact.
    solved = np.where(np.isfinite(critical), critical, 0.0)[:, None]
    surplus_cells = solved * basis[:, window] < earnings[:, window]
    grossed_up = tax_divisor[:, window] != 1.0
    has_surplus = bool(np.any(surplus_cells & grossed_up))

    kwargs = {
        "real_returns": real_returns,
        "fixed_flow": fixed_flow,
        "basis": basis,
        "earnings": earnings,
        "tax_divisor": tax_divisor,
        "window": window,
        "initial_portfolio": initial_portfolio,
        "target_net_worth": target_net_worth,
    }
    if has_surplus:
        critical = _refine_multipliers(critical, **kwargs)

    solve_years = len(range(*window.indices(basis.shape[1])))
    return _build_table(
        critical, basis_mean, target_net_worth, solve_years, phase_name, has_surplus
    )


def solve_safe_spending(
    params: SimulationInput,
    historical_data: npt.NDArray[np.float64],
    target_net_worth: float = 0.0,
    n_runs: int = 10_000,
    seed: int | None = None,
) -> SafeSpendingTable:
    """Safe-spending table for a single parameter set.

    The authored spending distribution is scaled up or down as a whole, so its
    shape is preserved and the reported figure is the resulting mean annual
    spend.
    """
    if target_net_worth < 0:
        raise ValueError("Target net worth must be non-negative")

    rng = np.random.default_rng(seed)
    years = params.years_to_simulate
    assert params.sample_years is not None

    total = params.cash_value + params.market_value + params.bond_value
    basis = sample_spending(params.spending_distribution, n_runs, years, rng)
    earnings = np.full((n_runs, years), params.earnings, dtype=np.float64)
    tax_divisor = np.full((n_runs, years), 1.0 / (1.0 - params.withdrawal_tax_rate))

    real_returns = _real_returns(
        rng,
        historical_data,
        n_runs,
        years,
        params.sample_years,
        params.market_value / total,
        params.bond_value / total,
    )

    return _solve(
        real_returns,
        basis,
        earnings,
        tax_divisor,
        slice(0, years),
        total,
        target_net_worth,
        phase_name=None,
    )


def solve_plan_safe_spending(
    parameter_sets: list[PlanParameterSet],
    years_to_simulate: int,
    sample_years: int,
    historical_data: npt.NDArray[np.float64],
    target_net_worth: float = 0.0,
    n_runs: int = 10_000,
    seed: int | None = None,
) -> SafeSpendingTable:
    """Safe-spending table for the final phase of a plan.

    Earlier phases describe life and career events that are already committed,
    so they are held exactly as authored; only the concluding phase — typically
    retirement — is solved for.
    """
    if not parameter_sets:
        raise ValueError("At least one parameter set is required")
    if target_net_worth < 0:
        raise ValueError("Target net worth must be non-negative")

    rng = np.random.default_rng(seed)
    phases = compute_phase_durations(parameter_sets, years_to_simulate)

    # Sample in the same order as run_plan_simulation so the two agree run-for-run.
    basis_parts: list[npt.NDArray[np.float64]] = []
    earnings_parts: list[npt.NDArray[np.float64]] = []
    tax_parts: list[npt.NDArray[np.float64]] = []
    for ps, phase_years in phases:
        basis_parts.append(sample_spending(ps.spending_distribution, n_runs, phase_years, rng))
        earnings_parts.append(np.full((n_runs, phase_years), ps.earnings, dtype=np.float64))
        tax_parts.append(
            np.full((n_runs, phase_years), 1.0 / (1.0 - ps.withdrawal_tax_rate), dtype=np.float64)
        )

    basis = np.concatenate(basis_parts, axis=1)
    earnings = np.concatenate(earnings_parts, axis=1)
    tax_divisor = np.concatenate(tax_parts, axis=1)

    first = parameter_sets[0]
    total = first.cash_value + first.market_value + first.bond_value
    real_returns = _real_returns(
        rng,
        historical_data,
        n_runs,
        years_to_simulate,
        sample_years,
        first.market_value / total,
        first.bond_value / total,
    )

    last_ps, last_years = phases[-1]
    window = slice(years_to_simulate - last_years, years_to_simulate)

    return _solve(
        real_returns,
        basis,
        earnings,
        tax_divisor,
        window,
        total,
        target_net_worth,
        phase_name=last_ps.name,
    )
