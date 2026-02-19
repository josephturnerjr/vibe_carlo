"""Plan simulation engine: multi-phase Monte Carlo simulation."""

import numpy as np
import numpy.typing as npt

from vibe_carlo.schemas import PlanParameterSet, SimulationResult
from vibe_carlo.simulation.distributions import sample_spending
from vibe_carlo.simulation.engine import _build_bootstrap_indices
from vibe_carlo.simulation.models import COL_BOND, COL_CPI, COL_SP500
from vibe_carlo.simulation.tax import gross_up_withdrawal_array


def run_plan_simulation(
    parameter_sets: list[PlanParameterSet],
    years_to_simulate: int,
    sample_years: int,
    historical_data: npt.NDArray[np.float64],
    n_runs: int = 10_000,
    seed: int | None = None,
) -> SimulationResult:
    """Run a multi-phase Monte Carlo simulation from ordered parameter sets.

    Each parameter set defines a phase with its own spending, earnings,
    and tax settings. The portfolio allocation comes from the first set.
    """
    if not parameter_sets:
        raise ValueError("At least one parameter set is required")

    rng = np.random.default_rng(seed)
    years = years_to_simulate

    # --- Compute effective phase durations ---
    phases: list[tuple[PlanParameterSet, int]] = []
    remaining = years
    for i, ps in enumerate(parameter_sets):
        if remaining <= 0:
            break
        is_last = i == len(parameter_sets) - 1
        if is_last or ps.duration is None:
            phase_years = remaining
        else:
            phase_years = min(ps.duration, remaining)
        phases.append((ps, phase_years))
        remaining -= phase_years

    # --- Build per-phase spending and earnings arrays ---
    spending_parts: list[npt.NDArray[np.float64]] = []
    earnings_parts: list[npt.NDArray[np.float64]] = []
    for ps, phase_years in phases:
        if phase_years == 0:
            continue
        spending = sample_spending(ps.spending_distribution, n_runs, phase_years, rng)
        spending_parts.append(spending)
        earnings_parts.append(np.full((n_runs, phase_years), ps.earnings, dtype=np.float64))

    spending_samples = np.concatenate(spending_parts, axis=1)  # (n_runs, years)
    earnings_array = np.concatenate(earnings_parts, axis=1)  # (n_runs, years)

    # --- Compute shortfall/surplus ---
    shortfall = np.maximum(spending_samples - earnings_array, 0.0)
    surplus = np.maximum(earnings_array - spending_samples, 0.0)

    # --- Per-phase tax gross-up ---
    gross_parts: list[npt.NDArray[np.float64]] = []
    col = 0
    for ps, phase_years in phases:
        if phase_years == 0:
            continue
        phase_shortfall = shortfall[:, col : col + phase_years]
        if ps.filing_status is not None:
            gross_parts.append(gross_up_withdrawal_array(phase_shortfall, ps.filing_status))
        else:
            gross_parts.append(phase_shortfall)
        col += phase_years

    gross_withdrawals = np.concatenate(gross_parts, axis=1)

    # --- Portfolio allocation from first parameter set ---
    first_ps = parameter_sets[0]
    total_portfolio = first_ps.cash_value + first_ps.market_value + first_ps.bond_value
    market_alloc = first_ps.market_value / total_portfolio
    bond_alloc = first_ps.bond_value / total_portfolio

    # --- Bootstrap indices ---
    n_historical = len(historical_data)
    sampled_indices = _build_bootstrap_indices(rng, n_runs, years, sample_years, n_historical)
    sampled_data = historical_data[sampled_indices]

    sp500_returns = sampled_data[:, :, COL_SP500]
    bond_returns = sampled_data[:, :, COL_BOND]
    cpi_inflation = sampled_data[:, :, COL_CPI]

    nominal_return = market_alloc * sp500_returns + bond_alloc * bond_returns
    real_return = (1 + nominal_return) / (1 + cpi_inflation) - 1

    # --- Year-by-year simulation ---
    portfolios = np.zeros((n_runs, years + 1), dtype=np.float64)
    portfolios[:, 0] = total_portfolio

    ever_hit_zero = np.zeros(n_runs, dtype=bool)

    for y in range(years):
        value = portfolios[:, y]
        value = value * (1 + real_return[:, y])
        value = value + surplus[:, y] - gross_withdrawals[:, y]
        value = np.maximum(value, 0.0)
        portfolios[:, y + 1] = value
        ever_hit_zero |= value == 0.0

    # --- Compute results ---
    success_rate = float(1.0 - np.mean(ever_hit_zero))

    p10 = np.percentile(portfolios, 10, axis=0).tolist()
    p25 = np.percentile(portfolios, 25, axis=0).tolist()
    p50 = np.percentile(portfolios, 50, axis=0).tolist()
    p75 = np.percentile(portfolios, 75, axis=0).tolist()
    p90 = np.percentile(portfolios, 90, axis=0).tolist()

    year_labels = list(range(years + 1))
    final_year_distribution = portfolios[:, -1].tolist()

    return SimulationResult(
        year_labels=year_labels,
        percentiles={
            "p10": p10,
            "p25": p25,
            "p50": p50,
            "p75": p75,
            "p90": p90,
        },
        success_rate=success_rate,
        final_year_distribution=final_year_distribution,
        gross_withdrawal=None,
        effective_tax_rate=None,
    )
