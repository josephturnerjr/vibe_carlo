"""Timeline computation: historical points, violin KDEs, and fan chart projections."""

from datetime import date, timedelta

import numpy as np
import numpy.typing as npt

from vibe_carlo.schemas import (
    FanChartData,
    SimulationInput,
    SnapshotRow,
    TimelineData,
    TimelinePoint,
    ViolinData,
)
from vibe_carlo.simulation.engine import run_simulation


def _net_value(snapshot: SnapshotRow) -> float:
    """Return total portfolio value: cash + market + bonds."""
    return snapshot.cash_value + snapshot.market_value + snapshot.bond_value


def _compute_year_gap(date_a: str, date_b: str) -> int:
    """Compute the number of years between two ISO date strings, minimum 1."""
    a = date.fromisoformat(date_a)
    b = date.fromisoformat(date_b)
    days = abs((b - a).days)
    years = round(days / 365.25)
    return max(1, years)


def _gaussian_kde(
    data: npt.NDArray[np.float64],
    eval_points: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Compute Gaussian KDE using Silverman bandwidth rule (numpy only)."""
    n = len(data)
    std = float(np.std(data, ddof=1))
    q75, q25 = float(np.percentile(data, 75)), float(np.percentile(data, 25))
    iqr = q75 - q25
    # Silverman's rule of thumb
    bw = 0.9 * min(std, iqr / 1.34) * n ** (-0.2)
    if bw <= 0:
        bw = std * n ** (-0.2) if std > 0 else 1.0

    # (n_eval, n_data) difference matrix
    diff = eval_points[:, np.newaxis] - data[np.newaxis, :]
    kernel = np.exp(-0.5 * (diff / bw) ** 2) / (bw * np.sqrt(2 * np.pi))
    density: npt.NDArray[np.float64] = np.mean(kernel, axis=1)
    return density


def _compute_kde(
    distribution: npt.NDArray[np.float64],
    n_points: int = 100,
) -> tuple[list[float], list[float]]:
    """Evaluate KDE from p1 to p99, normalize so max density = 1.0."""
    low = float(np.percentile(distribution, 1))
    high = float(np.percentile(distribution, 99))
    if low == high:
        return [float(low)], [1.0]
    eval_points = np.linspace(low, high, n_points)
    densities = _gaussian_kde(distribution, eval_points)
    max_d = float(np.max(densities))
    if max_d > 0:
        densities = densities / max_d
    return eval_points.tolist(), densities.tolist()


def _compute_percentile(
    distribution: npt.NDArray[np.float64],
    actual_value: float,
) -> float:
    """Compute what percentile actual_value falls at in the distribution (0-100)."""
    sorted_dist = np.sort(distribution)
    idx = int(np.searchsorted(sorted_dist, actual_value))
    return 100.0 * idx / len(sorted_dist)


def compute_timeline(
    snapshots: list[SnapshotRow],
    historical_data: npt.NDArray[np.float64],
    future_years: int = 30,
    n_runs: int = 10_000,
    seed: int | None = None,
) -> TimelineData:
    """Build timeline data from a list of snapshots (must be in ASC date order).

    For each consecutive pair of snapshots, runs a Monte Carlo simulation from
    the earlier snapshot's parameters over the year gap, then computes a KDE of
    the resulting distribution and the percentile of the actual outcome.

    For the newest snapshot, projects forward future_years to build a fan chart.
    """
    points: list[TimelinePoint] = []
    violins: list[ViolinData] = []

    # Build TimelinePoints
    for i, snap in enumerate(snapshots):
        points.append(
            TimelinePoint(
                date=snap.snapshot_date,
                value=_net_value(snap),
                name=snap.name,
                snapshot_id=snap.id,
                percentile=None,  # filled in below for i > 0
            )
        )

    # For each consecutive pair, run simulation and compute violin + percentile
    for i in range(1, len(snapshots)):
        earlier = snapshots[i - 1]
        later = snapshots[i]
        year_gap = _compute_year_gap(earlier.snapshot_date, later.snapshot_date)

        sim_input = SimulationInput(
            cash_value=earlier.cash_value,
            market_value=earlier.market_value,
            bond_value=earlier.bond_value,
            earnings=earlier.earnings,
            spending_distribution=earlier.spending_distribution,
            years_to_simulate=year_gap,
            sample_years=earlier.sample_years,
            filing_status=earlier.filing_status,
        )
        result = run_simulation(sim_input, historical_data, n_runs=n_runs, seed=seed)

        dist = np.array(result.final_year_distribution, dtype=np.float64)
        actual = _net_value(later)

        points[i].percentile = _compute_percentile(dist, actual)

        values, densities = _compute_kde(dist)
        violins.append(
            ViolinData(
                date=later.snapshot_date,
                values=values,
                densities=densities,
            )
        )

    # Fan chart from newest snapshot
    fan_chart: FanChartData | None = None
    if snapshots:
        newest = snapshots[-1]
        sim_input = SimulationInput(
            cash_value=newest.cash_value,
            market_value=newest.market_value,
            bond_value=newest.bond_value,
            earnings=newest.earnings,
            spending_distribution=newest.spending_distribution,
            years_to_simulate=future_years,
            sample_years=newest.sample_years,
            filing_status=newest.filing_status,
        )
        result = run_simulation(sim_input, historical_data, n_runs=n_runs, seed=seed)

        base_date = date.fromisoformat(newest.snapshot_date)
        fan_dates = [
            (base_date + timedelta(days=int(y * 365.25))).isoformat() for y in result.year_labels
        ]
        fan_chart = FanChartData(
            dates=fan_dates,
            p10=result.percentiles["p10"],
            p25=result.percentiles["p25"],
            p50=result.percentiles["p50"],
            p75=result.percentiles["p75"],
            p90=result.percentiles["p90"],
        )

    return TimelineData(points=points, violins=violins, fan_chart=fan_chart)
