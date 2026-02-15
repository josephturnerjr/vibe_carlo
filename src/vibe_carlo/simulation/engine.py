import numpy as np
import numpy.typing as npt

from vibe_carlo.schemas import SimulationInput, SimulationResult
from vibe_carlo.simulation.distributions import sample_spending
from vibe_carlo.simulation.models import COL_BOND, COL_CPI, COL_SP500
from vibe_carlo.simulation.tax import gross_up_withdrawal_array


def run_simulation(
    params: SimulationInput,
    historical_data: npt.NDArray[np.float64],
    n_runs: int = 10_000,
    seed: int | None = None,
) -> SimulationResult:
    """Run Monte Carlo simulation with block bootstrap resampling."""
    rng = np.random.default_rng(seed)

    years = params.years_to_simulate
    assert params.sample_years is not None
    block_len = params.sample_years
    n_historical = len(historical_data)

    # Sample spending: shape (n_runs, years)
    spending_samples = sample_spending(params.spending_distribution, n_runs, years, rng)

    # Earnings cover spending first; only the shortfall requires a portfolio withdrawal
    shortfall = np.maximum(spending_samples - params.earnings, 0.0)
    surplus = np.maximum(params.earnings - spending_samples, 0.0)

    # Compute gross withdrawals (pre-tax) if tax adjustment is active
    if params.filing_status is not None:
        gross_withdrawals = gross_up_withdrawal_array(
            shortfall,
            params.filing_status,
        )
    else:
        gross_withdrawals = shortfall

    total_portfolio = params.cash_value + params.market_value + params.bond_value
    market_alloc = params.market_value / total_portfolio
    bond_alloc = params.bond_value / total_portfolio

    # Build sampled return indices for all runs: shape (n_runs, years)
    sampled_indices = _build_bootstrap_indices(rng, n_runs, years, block_len, n_historical)

    # Gather the historical data for all runs: shape (n_runs, years, 3)
    sampled_data = historical_data[sampled_indices]

    sp500_returns = sampled_data[:, :, COL_SP500]  # (n_runs, years)
    bond_returns = sampled_data[:, :, COL_BOND]  # (n_runs, years)
    cpi_inflation = sampled_data[:, :, COL_CPI]  # (n_runs, years)

    # Blended nominal return
    nominal_return = market_alloc * sp500_returns + bond_alloc * bond_returns

    # Real return: deflate by CPI
    real_return = (1 + nominal_return) / (1 + cpi_inflation) - 1

    # Simulate year-by-year: portfolio compounds with real returns
    portfolios = np.zeros((n_runs, years + 1), dtype=np.float64)
    portfolios[:, 0] = total_portfolio

    # Track whether each run has ever hit zero
    ever_hit_zero = np.zeros(n_runs, dtype=bool)

    for y in range(years):
        value = portfolios[:, y]
        value = value * (1 + real_return[:, y])
        value = value + surplus[:, y] - gross_withdrawals[:, y]
        value = np.maximum(value, 0.0)
        portfolios[:, y + 1] = value
        ever_hit_zero |= value == 0.0

    # Success = portfolio never touched $0
    success_rate = float(1.0 - np.mean(ever_hit_zero))

    # Percentile time series (include year 0)
    p10 = np.percentile(portfolios, 10, axis=0).tolist()
    p25 = np.percentile(portfolios, 25, axis=0).tolist()
    p50 = np.percentile(portfolios, 50, axis=0).tolist()
    p75 = np.percentile(portfolios, 75, axis=0).tolist()
    p90 = np.percentile(portfolios, 90, axis=0).tolist()

    year_labels = list(range(years + 1))
    final_year_distribution = portfolios[:, -1].tolist()

    # Tax info for results (only when tax adjustment is active)
    result_gross: float | None = None
    result_etr: float | None = None
    if params.filing_status is not None:
        mean_gross = float(np.mean(gross_withdrawals))
        mean_shortfall = float(np.mean(shortfall))
        result_gross = mean_gross
        if mean_gross > 0:
            result_etr = (mean_gross - mean_shortfall) / mean_gross
        else:
            result_etr = 0.0

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
        gross_withdrawal=result_gross,
        effective_tax_rate=result_etr,
    )


def _build_bootstrap_indices(
    rng: np.random.Generator,
    n_runs: int,
    years: int,
    block_len: int,
    n_historical: int,
) -> npt.NDArray[np.intp]:
    """Build bootstrap sample indices as contiguous blocks.

    Returns an (n_runs, years) array of indices into the historical data.
    """
    max_start = n_historical - block_len
    indices = np.empty((n_runs, years), dtype=np.intp)

    col = 0
    while col < years:
        remaining = years - col
        current_block = min(block_len, remaining)
        starts = rng.integers(0, max_start + 1, size=n_runs)
        for offset in range(current_block):
            indices[:, col + offset] = starts + offset
        col += current_block

    return indices
