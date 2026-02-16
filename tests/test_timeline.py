"""Unit tests for timeline computation module."""

import numpy as np

from vibe_carlo.schemas import FlatDistribution, SnapshotRow
from vibe_carlo.simulation.models import load_historical_data
from vibe_carlo.timeline import (
    _compute_kde,
    _compute_percentile,
    _compute_year_gap,
    _gaussian_kde,
    _net_value,
    compute_timeline,
)


def _make_snapshot(
    snapshot_id: int = 1,
    name: str | None = None,
    date: str = "2025-01-01",
    cash: float = 100_000.0,
    market: float = 500_000.0,
    bonds: float = 50_000.0,
    earnings: float = 0.0,
    spending: float = 0.0,
    years: int = 30,
) -> SnapshotRow:
    return SnapshotRow(
        id=snapshot_id,
        name=name,
        snapshot_date=date,
        cash_value=cash,
        market_value=market,
        bond_value=bonds,
        earnings=earnings,
        spending_distribution=FlatDistribution(value=spending),
        years_to_simulate=years,
    )


# --- _net_value ---


def test_net_value() -> None:
    snap = _make_snapshot(cash=100, market=200, bonds=300)
    assert _net_value(snap) == 600.0


def test_net_value_zeros() -> None:
    snap = _make_snapshot(cash=0, market=500_000, bonds=0)
    assert _net_value(snap) == 500_000.0


# --- _compute_year_gap ---


def test_year_gap_exact() -> None:
    assert _compute_year_gap("2020-01-01", "2023-01-01") == 3


def test_year_gap_partial() -> None:
    # 547 days / 365.25 = 1.497 → rounds to 1
    assert _compute_year_gap("2020-01-01", "2021-07-01") == 1
    # 912 days / 365.25 = 2.496 → rounds to 2
    assert _compute_year_gap("2020-01-01", "2022-07-01") == 2


def test_year_gap_same_date() -> None:
    # 0 days rounds to 0, but min is 1
    assert _compute_year_gap("2025-06-15", "2025-06-15") == 1


def test_year_gap_far_apart() -> None:
    assert _compute_year_gap("2000-01-01", "2030-01-01") == 30


def test_year_gap_reversed() -> None:
    # Order shouldn't matter (uses abs)
    assert _compute_year_gap("2023-01-01", "2020-01-01") == 3


# --- _compute_percentile ---


def test_percentile_low_value() -> None:
    dist = np.arange(100, dtype=np.float64)
    p = _compute_percentile(dist, 5.0)
    assert 0 <= p <= 15  # should be around 5-6


def test_percentile_mid_value() -> None:
    dist = np.arange(100, dtype=np.float64)
    p = _compute_percentile(dist, 50.0)
    assert 40 <= p <= 60


def test_percentile_high_value() -> None:
    dist = np.arange(100, dtype=np.float64)
    p = _compute_percentile(dist, 95.0)
    assert 85 <= p <= 100


def test_percentile_below_all() -> None:
    dist = np.arange(10, 100, dtype=np.float64)
    p = _compute_percentile(dist, 0.0)
    assert p == 0.0


def test_percentile_above_all() -> None:
    dist = np.arange(100, dtype=np.float64)
    p = _compute_percentile(dist, 1000.0)
    assert p == 100.0


# --- _gaussian_kde ---


def test_kde_correct_shape() -> None:
    data = np.random.default_rng(42).normal(100, 10, size=500)
    eval_pts = np.linspace(60, 140, 50)
    density = _gaussian_kde(data, eval_pts)
    assert density.shape == (50,)


def test_kde_peak_near_mean() -> None:
    rng = np.random.default_rng(42)
    data = rng.normal(100, 10, size=1000)
    eval_pts = np.linspace(60, 140, 200)
    density = _gaussian_kde(data, eval_pts)
    peak_idx = int(np.argmax(density))
    peak_x = eval_pts[peak_idx]
    assert 90 <= peak_x <= 110


def test_kde_all_positive() -> None:
    data = np.random.default_rng(42).normal(0, 1, size=200)
    eval_pts = np.linspace(-3, 3, 50)
    density = _gaussian_kde(data, eval_pts)
    assert np.all(density > 0)


# --- _compute_kde ---


def test_compute_kde_normalized() -> None:
    dist = np.random.default_rng(42).normal(500_000, 50_000, size=1000)
    values, densities = _compute_kde(dist)
    assert len(values) == len(densities)
    assert max(densities) == 1.0
    assert all(0 <= d <= 1.0 for d in densities)


def test_compute_kde_degenerate() -> None:
    # All same values
    dist = np.full(100, 42.0)
    values, densities = _compute_kde(dist)
    assert len(values) == 1
    assert values[0] == 42.0
    assert densities[0] == 1.0


# --- compute_timeline integration ---


def test_single_snapshot() -> None:
    data = load_historical_data()
    snap = _make_snapshot(snapshot_id=1, date="2025-01-01")
    result = compute_timeline([snap], data, future_years=10, n_runs=100, seed=42)

    assert len(result.points) == 1
    assert result.points[0].percentile is None
    assert len(result.violins) == 0
    assert result.fan_chart is not None
    assert len(result.fan_chart.dates) == 11  # 0..10


def test_two_snapshots() -> None:
    data = load_historical_data()
    s1 = _make_snapshot(snapshot_id=1, date="2024-01-01", market=500_000)
    s2 = _make_snapshot(snapshot_id=2, date="2025-01-01", market=550_000)
    result = compute_timeline([s1, s2], data, future_years=10, n_runs=100, seed=42)

    assert len(result.points) == 2
    assert result.points[0].percentile is None
    assert result.points[1].percentile is not None
    assert 0 <= result.points[1].percentile <= 100
    assert len(result.violins) == 1
    assert result.violins[0].date == "2025-01-01"
    assert result.fan_chart is not None


def test_three_snapshots() -> None:
    data = load_historical_data()
    s1 = _make_snapshot(snapshot_id=1, date="2023-01-01", market=400_000)
    s2 = _make_snapshot(snapshot_id=2, date="2024-01-01", market=500_000)
    s3 = _make_snapshot(snapshot_id=3, date="2025-01-01", market=550_000)
    result = compute_timeline([s1, s2, s3], data, future_years=10, n_runs=100, seed=42)

    assert len(result.points) == 3
    assert len(result.violins) == 2
    assert result.violins[0].date == "2024-01-01"
    assert result.violins[1].date == "2025-01-01"


def test_fan_chart_30_years() -> None:
    data = load_historical_data()
    snap = _make_snapshot(snapshot_id=1, date="2025-01-01")
    result = compute_timeline([snap], data, future_years=30, n_runs=100, seed=42)

    assert result.fan_chart is not None
    assert len(result.fan_chart.dates) == 31
    assert result.fan_chart.dates[0] == "2025-01-01"
    # Last date should be ~30 years later
    assert result.fan_chart.dates[-1].startswith("2054") or result.fan_chart.dates[-1].startswith(
        "2055"
    )


def test_deterministic_with_seed() -> None:
    data = load_historical_data()
    snap = _make_snapshot(snapshot_id=1, date="2025-01-01")
    r1 = compute_timeline([snap], data, future_years=5, n_runs=100, seed=123)
    r2 = compute_timeline([snap], data, future_years=5, n_runs=100, seed=123)

    assert r1.fan_chart is not None
    assert r2.fan_chart is not None
    assert r1.fan_chart.p50 == r2.fan_chart.p50


def test_violin_dates_match_later_snapshots() -> None:
    data = load_historical_data()
    s1 = _make_snapshot(snapshot_id=1, date="2023-06-01")
    s2 = _make_snapshot(snapshot_id=2, date="2024-06-01")
    s3 = _make_snapshot(snapshot_id=3, date="2025-06-01")
    result = compute_timeline([s1, s2, s3], data, n_runs=100, seed=42)

    assert [v.date for v in result.violins] == ["2024-06-01", "2025-06-01"]


def test_fan_chart_starts_at_newest_snapshot_value() -> None:
    data = load_historical_data()
    snap = _make_snapshot(snapshot_id=1, date="2025-03-15", cash=100, market=900, bonds=0)
    result = compute_timeline([snap], data, future_years=5, n_runs=100, seed=42)

    assert result.fan_chart is not None
    # Year 0 of fan chart = starting portfolio value across all percentiles
    total = 100 + 900
    assert result.fan_chart.p10[0] == total
    assert result.fan_chart.p50[0] == total
    assert result.fan_chart.p90[0] == total
