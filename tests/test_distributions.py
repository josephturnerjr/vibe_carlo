import numpy as np
import pytest

from vibe_carlo.schemas import (
    FlatDistribution,
    TruncatedNormalDistribution,
    UniformDistribution,
)
from vibe_carlo.simulation.distributions import sample_spending


def test_flat_shape_and_value() -> None:
    dist = FlatDistribution(value=50_000.0)
    rng = np.random.default_rng(42)
    result = sample_spending(dist, n_runs=100, years=30, rng=rng)
    assert result.shape == (100, 30)
    assert np.all(result == 50_000.0)


def test_flat_zero() -> None:
    dist = FlatDistribution(value=0.0)
    rng = np.random.default_rng(42)
    result = sample_spending(dist, n_runs=10, years=5, rng=rng)
    assert np.all(result == 0.0)


def test_uniform_shape_and_bounds() -> None:
    dist = UniformDistribution(low=40_000.0, high=60_000.0)
    rng = np.random.default_rng(42)
    result = sample_spending(dist, n_runs=1000, years=30, rng=rng)
    assert result.shape == (1000, 30)
    assert np.all(result >= 40_000.0)
    assert np.all(result <= 60_000.0)


def test_uniform_mean_approx() -> None:
    dist = UniformDistribution(low=40_000.0, high=60_000.0)
    rng = np.random.default_rng(42)
    result = sample_spending(dist, n_runs=10_000, years=1, rng=rng)
    assert np.mean(result) == pytest.approx(50_000.0, rel=0.02)


def test_uniform_equal_bounds() -> None:
    dist = UniformDistribution(low=50_000.0, high=50_000.0)
    rng = np.random.default_rng(42)
    result = sample_spending(dist, n_runs=10, years=5, rng=rng)
    assert np.all(result == 50_000.0)


def test_truncated_normal_shape_and_bounds() -> None:
    dist = TruncatedNormalDistribution(low=35_000.0, high=65_000.0, mean=50_000.0, stddev=5_000.0)
    rng = np.random.default_rng(42)
    result = sample_spending(dist, n_runs=1000, years=30, rng=rng)
    assert result.shape == (1000, 30)
    assert np.all(result >= 35_000.0)
    assert np.all(result <= 65_000.0)


def test_truncated_normal_mean_approx() -> None:
    dist = TruncatedNormalDistribution(low=35_000.0, high=65_000.0, mean=50_000.0, stddev=5_000.0)
    rng = np.random.default_rng(42)
    result = sample_spending(dist, n_runs=10_000, years=1, rng=rng)
    assert np.mean(result) == pytest.approx(50_000.0, rel=0.02)


def test_truncated_normal_deterministic() -> None:
    dist = TruncatedNormalDistribution(low=35_000.0, high=65_000.0, mean=50_000.0, stddev=5_000.0)
    r1 = sample_spending(dist, n_runs=50, years=10, rng=np.random.default_rng(99))
    r2 = sample_spending(dist, n_runs=50, years=10, rng=np.random.default_rng(99))
    np.testing.assert_array_equal(r1, r2)


def test_uniform_validation_low_gt_high() -> None:
    with pytest.raises(ValueError, match="low must be"):
        UniformDistribution(low=60_000.0, high=40_000.0)


def test_truncated_normal_validation_mean_outside_bounds() -> None:
    with pytest.raises(ValueError, match="mean must be within"):
        TruncatedNormalDistribution(low=40_000.0, high=60_000.0, mean=70_000.0, stddev=5_000.0)


def test_truncated_normal_validation_zero_stddev() -> None:
    with pytest.raises(ValueError):
        TruncatedNormalDistribution(low=40_000.0, high=60_000.0, mean=50_000.0, stddev=0.0)
