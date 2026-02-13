import numpy as np

from vibe_carlo.schemas import FlatDistribution, SimulationInput, UniformDistribution
from vibe_carlo.simulation.engine import run_simulation
from vibe_carlo.simulation.models import load_historical_data


def _make_params(**overrides: object) -> SimulationInput:
    defaults: dict[str, object] = {
        "cash_value": 10_000.0,
        "market_value": 70_000.0,
        "bond_value": 20_000.0,
        "annual_contribution": 12_000.0,
        "spending_distribution": FlatDistribution(value=0.0),
        "years_to_simulate": 30,
    }
    defaults.update(overrides)
    return SimulationInput(**defaults)  # type: ignore[arg-type]


def test_output_shape() -> None:
    data = load_historical_data()
    params = _make_params()
    result = run_simulation(params, data, n_runs=100, seed=42)

    assert len(result.year_labels) == 31  # 0..30
    for key in ("p10", "p25", "p50", "p75", "p90"):
        assert len(result.percentiles[key]) == 31
    assert len(result.final_year_distribution) == 100


def test_percentile_ordering() -> None:
    data = load_historical_data()
    params = _make_params()
    result = run_simulation(params, data, n_runs=1000, seed=42)

    for i in range(len(result.year_labels)):
        assert result.percentiles["p10"][i] <= result.percentiles["p25"][i]
        assert result.percentiles["p25"][i] <= result.percentiles["p50"][i]
        assert result.percentiles["p50"][i] <= result.percentiles["p75"][i]
        assert result.percentiles["p75"][i] <= result.percentiles["p90"][i]


def test_success_rate_bounds() -> None:
    data = load_historical_data()
    params = _make_params()
    result = run_simulation(params, data, n_runs=1000, seed=42)

    assert 0.0 <= result.success_rate <= 1.0


def test_high_spending_lowers_success() -> None:
    data = load_historical_data()
    params = _make_params(
        spending_distribution=FlatDistribution(value=50_000.0),
        annual_contribution=0.0,
    )
    result = run_simulation(params, data, n_runs=1000, seed=42)

    assert result.success_rate < 1.0


def test_zero_spending_with_contributions() -> None:
    data = load_historical_data()
    params = _make_params(
        spending_distribution=FlatDistribution(value=0.0),
        annual_contribution=20_000.0,
    )
    result = run_simulation(params, data, n_runs=1000, seed=42)

    assert result.success_rate == 1.0


def test_all_bonds_portfolio() -> None:
    data = load_historical_data()
    params = _make_params(cash_value=0.0, market_value=0.0, bond_value=100_000.0)
    result = run_simulation(params, data, n_runs=100, seed=42)

    assert len(result.year_labels) == 31


def test_all_cash_portfolio() -> None:
    data = load_historical_data()
    params = _make_params(cash_value=100_000.0, market_value=0.0, bond_value=0.0)
    result = run_simulation(params, data, n_runs=100, seed=42)

    assert result.percentiles["p50"][-1] < 100_000.0 * 30


def test_deterministic_with_seed() -> None:
    data = load_historical_data()
    params = _make_params()
    r1 = run_simulation(params, data, n_runs=100, seed=123)
    r2 = run_simulation(params, data, n_runs=100, seed=123)

    assert r1.success_rate == r2.success_rate
    assert r1.percentiles == r2.percentiles


def test_sample_years_smaller_than_simulation() -> None:
    data = load_historical_data()
    params = _make_params(years_to_simulate=30, sample_years=10)
    result = run_simulation(params, data, n_runs=100, seed=42)

    assert len(result.year_labels) == 31


def test_portfolio_floor_at_zero() -> None:
    data = load_historical_data()
    params = _make_params(
        cash_value=0.0,
        market_value=100.0,
        bond_value=0.0,
        spending_distribution=FlatDistribution(value=1_000_000.0),
        annual_contribution=0.0,
    )
    result = run_simulation(params, data, n_runs=100, seed=42)

    assert all(v == 0.0 for v in result.final_year_distribution)
    assert result.success_rate == 0.0


def test_year_labels_start_at_zero() -> None:
    data = load_historical_data()
    params = _make_params(years_to_simulate=5)
    result = run_simulation(params, data, n_runs=100, seed=42)

    assert result.year_labels == [0, 1, 2, 3, 4, 5]


def test_starting_value_correct() -> None:
    data = load_historical_data()
    params = _make_params()
    result = run_simulation(params, data, n_runs=100, seed=42)

    total = 10_000.0 + 70_000.0 + 20_000.0
    for key in ("p10", "p25", "p50", "p75", "p90"):
        assert result.percentiles[key][0] == total


def test_tax_enabled_increases_effective_withdrawal() -> None:
    data = load_historical_data()
    params_no_tax = _make_params(
        cash_value=0.0,
        market_value=1_000_000.0,
        bond_value=0.0,
        spending_distribution=FlatDistribution(value=50_000.0),
        annual_contribution=0.0,
    )
    params_tax = _make_params(
        cash_value=0.0,
        market_value=1_000_000.0,
        bond_value=0.0,
        spending_distribution=FlatDistribution(value=50_000.0),
        annual_contribution=0.0,
        filing_status="single",
        other_income=0.0,
    )
    result_no_tax = run_simulation(params_no_tax, data, n_runs=1000, seed=42)
    result_tax = run_simulation(params_tax, data, n_runs=1000, seed=42)

    assert result_tax.success_rate < result_no_tax.success_rate
    assert result_tax.gross_withdrawal is not None
    assert result_tax.gross_withdrawal > 50_000.0
    assert result_tax.effective_tax_rate is not None
    assert result_tax.effective_tax_rate > 0.0


def test_filing_status_none_identical_to_omitted() -> None:
    data = load_historical_data()
    params_omitted = _make_params(
        spending_distribution=FlatDistribution(value=40_000.0),
        annual_contribution=0.0,
    )
    params_none = _make_params(
        spending_distribution=FlatDistribution(value=40_000.0),
        annual_contribution=0.0,
        filing_status=None,
    )
    result_omitted = run_simulation(params_omitted, data, n_runs=100, seed=42)
    result_none = run_simulation(params_none, data, n_runs=100, seed=42)

    assert result_omitted.success_rate == result_none.success_rate
    assert result_omitted.gross_withdrawal is None
    assert result_none.gross_withdrawal is None


def test_historical_data_shape() -> None:
    data = load_historical_data()
    assert data.ndim == 2
    assert data.shape[1] == 3
    assert data.shape[0] >= 90
    assert not np.isnan(data).any()


def test_uniform_distribution_produces_variable_results() -> None:
    """Uniform spending distribution should produce different outcomes than flat."""
    data = load_historical_data()
    params_flat = _make_params(
        cash_value=0.0,
        market_value=500_000.0,
        bond_value=0.0,
        spending_distribution=FlatDistribution(value=50_000.0),
        annual_contribution=0.0,
        years_to_simulate=10,
    )
    params_uniform = _make_params(
        cash_value=0.0,
        market_value=500_000.0,
        bond_value=0.0,
        spending_distribution=UniformDistribution(low=40_000.0, high=60_000.0),
        annual_contribution=0.0,
        years_to_simulate=10,
    )
    result_flat = run_simulation(params_flat, data, n_runs=1000, seed=42)
    result_uniform = run_simulation(params_uniform, data, n_runs=1000, seed=42)

    # Both should run successfully
    assert 0.0 <= result_flat.success_rate <= 1.0
    assert 0.0 <= result_uniform.success_rate <= 1.0
    # Results won't be identical due to different spending patterns
    assert result_flat.percentiles["p50"] != result_uniform.percentiles["p50"]
