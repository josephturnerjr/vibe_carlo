import numpy as np
import pytest

from vibe_carlo.schemas import FilingStatus
from vibe_carlo.simulation.tax import (
    compute_tax,
    gross_up_withdrawal,
    gross_up_withdrawal_array,
)

# ---------------------------------------------------------------------------
# compute_tax tests
# ---------------------------------------------------------------------------


def test_compute_tax_zero_income() -> None:
    assert compute_tax(0, FilingStatus.single) == 0.0


def test_compute_tax_single_first_bracket() -> None:
    # 10,000 * 10% = 1,000
    assert compute_tax(10_000, FilingStatus.single) == pytest.approx(1_000.0)


def test_compute_tax_single_two_brackets() -> None:
    # 12,400 * 10% + 17,600 * 12% = 1,240 + 2,112 = 3,352
    assert compute_tax(30_000, FilingStatus.single) == pytest.approx(3_352.0)


def test_compute_tax_married_jointly_first_bracket() -> None:
    # 20,000 * 10% = 2,000
    assert compute_tax(20_000, FilingStatus.married_jointly) == pytest.approx(2_000.0)


# ---------------------------------------------------------------------------
# gross_up_withdrawal tests
# ---------------------------------------------------------------------------


def test_gross_up_zero_spending() -> None:
    assert gross_up_withdrawal(0, FilingStatus.single) == 0.0


def test_gross_up_within_standard_deduction() -> None:
    # $10K desired with $16,100 deduction → all tax-free
    assert gross_up_withdrawal(10_000, FilingStatus.single) == pytest.approx(10_000.0)


def test_gross_up_exactly_standard_deduction() -> None:
    # Single standard deduction = $16,100
    assert gross_up_withdrawal(16_100, FilingStatus.single) == pytest.approx(16_100.0)


def _round_trip_verify(desired: float, filing_status: FilingStatus) -> None:
    """Verify that gross - tax(gross) = desired_spending."""
    gross = gross_up_withdrawal(desired, filing_status)
    std_ded = 16_100.0
    if filing_status == FilingStatus.married_jointly:
        std_ded = 32_200.0
    elif filing_status == FilingStatus.head_of_household:
        std_ded = 24_150.0

    tax = compute_tax(max(0, gross - std_ded), filing_status)
    after_tax = gross - tax
    assert after_tax == pytest.approx(desired, abs=0.01)


def test_gross_up_200k_single() -> None:
    gross = gross_up_withdrawal(200_000, FilingStatus.single)
    assert gross == pytest.approx(251_918.0, abs=1.0)
    _round_trip_verify(200_000, FilingStatus.single)


def test_gross_up_round_trip_200k() -> None:
    _round_trip_verify(200_000, FilingStatus.single)


def test_gross_up_married_jointly_wider_brackets() -> None:
    gross_single = gross_up_withdrawal(100_000, FilingStatus.single)
    gross_married = gross_up_withdrawal(100_000, FilingStatus.married_jointly)
    # Married jointly has wider brackets → less tax → lower gross
    assert gross_married < gross_single
    _round_trip_verify(100_000, FilingStatus.married_jointly)


def test_gross_up_head_of_household() -> None:
    _round_trip_verify(80_000, FilingStatus.head_of_household)


def test_gross_up_married_separately() -> None:
    _round_trip_verify(60_000, FilingStatus.married_separately)


# ---------------------------------------------------------------------------
# gross_up_withdrawal_array tests (vectorized)
# ---------------------------------------------------------------------------


def test_array_matches_scalar_single() -> None:
    """Vectorized results should match scalar for a range of values."""
    values = [0.0, 10_000.0, 50_000.0, 100_000.0, 200_000.0]
    arr = np.array(values)
    result = gross_up_withdrawal_array(arr, FilingStatus.single)
    for i, v in enumerate(values):
        expected = gross_up_withdrawal(v, FilingStatus.single)
        assert result[i] == pytest.approx(expected, abs=0.01)


def test_array_2d_shape() -> None:
    arr = np.array([[50_000.0, 60_000.0], [70_000.0, 80_000.0]])
    result = gross_up_withdrawal_array(arr, FilingStatus.married_jointly)
    assert result.shape == (2, 2)
    for i in range(2):
        for j in range(2):
            expected = gross_up_withdrawal(arr[i, j], FilingStatus.married_jointly)
            assert result[i, j] == pytest.approx(expected, abs=0.01)


def test_array_all_zeros() -> None:
    arr = np.zeros((5, 3))
    result = gross_up_withdrawal_array(arr, FilingStatus.single)
    assert np.all(result == 0.0)


def test_array_large_values() -> None:
    arr = np.array([1_000_000.0])
    result = gross_up_withdrawal_array(arr, FilingStatus.single)
    expected = gross_up_withdrawal(1_000_000.0, FilingStatus.single)
    assert result[0] == pytest.approx(expected, abs=0.01)
