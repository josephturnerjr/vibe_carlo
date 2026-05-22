import numpy as np
import pytest

from vibe_carlo.schemas import FilingStatus
from vibe_carlo.simulation.tax import gross_up_withdrawal_array


def _gross(desired: float, filing_status: FilingStatus) -> float:
    """Helper: gross-up a single value via the array API."""
    return float(gross_up_withdrawal_array(np.array([desired], dtype=np.float64), filing_status)[0])


# ---------------------------------------------------------------------------
# Boundary / single-value behavior
# ---------------------------------------------------------------------------


def test_zero_spending() -> None:
    assert _gross(0, FilingStatus.single) == 0.0


def test_within_standard_deduction() -> None:
    # $10K desired with $16,100 deduction → all tax-free
    assert _gross(10_000, FilingStatus.single) == pytest.approx(10_000.0)


def test_exactly_standard_deduction() -> None:
    # Single standard deduction = $16,100
    assert _gross(16_100, FilingStatus.single) == pytest.approx(16_100.0)


def test_200k_single_anchor() -> None:
    # Anchor value: 200k after-tax requires ~251,918 gross under 2026 brackets.
    assert _gross(200_000, FilingStatus.single) == pytest.approx(251_918.0, abs=1.0)


def test_married_jointly_lower_gross_than_single() -> None:
    # Married jointly has wider brackets → less tax → lower gross.
    assert _gross(100_000, FilingStatus.married_jointly) < _gross(100_000, FilingStatus.single)


@pytest.mark.parametrize("filing_status", list(FilingStatus))
def test_gross_at_least_desired(filing_status: FilingStatus) -> None:
    # Tax is non-negative, so gross >= desired for any filing status.
    assert _gross(80_000, filing_status) >= 80_000


# ---------------------------------------------------------------------------
# Array shape / vectorized behavior
# ---------------------------------------------------------------------------


def test_array_preserves_1d_shape() -> None:
    values = np.array([0.0, 10_000.0, 50_000.0, 100_000.0, 200_000.0])
    result = gross_up_withdrawal_array(values, FilingStatus.single)
    assert result.shape == values.shape


def test_array_preserves_2d_shape() -> None:
    arr = np.array([[50_000.0, 60_000.0], [70_000.0, 80_000.0]])
    result = gross_up_withdrawal_array(arr, FilingStatus.married_jointly)
    assert result.shape == (2, 2)


def test_array_all_zeros() -> None:
    arr = np.zeros((5, 3))
    result = gross_up_withdrawal_array(arr, FilingStatus.single)
    assert np.all(result == 0.0)


def test_array_monotonic() -> None:
    # Higher desired spending → higher gross.
    arr = np.array([10_000.0, 50_000.0, 100_000.0, 250_000.0, 1_000_000.0])
    result = gross_up_withdrawal_array(arr, FilingStatus.single)
    assert np.all(np.diff(result) > 0)
