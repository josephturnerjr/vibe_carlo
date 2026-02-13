"""Sampling functions for spending distributions."""

import numpy as np
import numpy.typing as npt

from vibe_carlo.schemas import (
    FlatDistribution,
    SpendingDistribution,
    TruncatedNormalDistribution,
    UniformDistribution,
)


def sample_spending(
    dist: SpendingDistribution,
    n_runs: int,
    years: int,
    rng: np.random.Generator,
) -> npt.NDArray[np.float64]:
    """Sample spending values for each run and year.

    Returns an array of shape (n_runs, years).
    """
    shape = (n_runs, years)

    if isinstance(dist, FlatDistribution):
        return np.full(shape, dist.value, dtype=np.float64)

    if isinstance(dist, UniformDistribution):
        return rng.uniform(dist.low, dist.high, size=shape)

    if isinstance(dist, TruncatedNormalDistribution):
        return _sample_truncated_normal(dist, shape, rng)

    raise TypeError(f"Unknown distribution type: {type(dist)}")  # pragma: no cover


def _sample_truncated_normal(
    dist: TruncatedNormalDistribution,
    shape: tuple[int, int],
    rng: np.random.Generator,
) -> npt.NDArray[np.float64]:
    """Rejection sampling for truncated normal distribution."""
    total = shape[0] * shape[1]
    result = np.empty(total, dtype=np.float64)
    filled = 0

    while filled < total:
        needed = total - filled
        # Over-sample to reduce iterations (factor based on truncation severity)
        batch_size = int(needed * 1.5) + 100
        candidates = rng.normal(dist.mean, dist.stddev, size=batch_size)
        valid = candidates[(candidates >= dist.low) & (candidates <= dist.high)]
        take = min(len(valid), needed)
        result[filled : filled + take] = valid[:take]
        filled += take

    return result.reshape(shape)
