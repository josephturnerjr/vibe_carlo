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
    assert gross_up_withdrawal(0, FilingStatus.single, 0) == 0.0


def test_gross_up_within_standard_deduction() -> None:
    # $10K desired with $16,100 deduction → all tax-free
    assert gross_up_withdrawal(10_000, FilingStatus.single, 0) == pytest.approx(10_000.0)


def test_gross_up_exactly_standard_deduction() -> None:
    # Single standard deduction = $16,100
    assert gross_up_withdrawal(16_100, FilingStatus.single, 0) == pytest.approx(16_100.0)


def _round_trip_verify(desired: float, filing_status: FilingStatus, other_income: float) -> None:
    """Verify that gross - marginal_tax = desired_spending."""
    gross = gross_up_withdrawal(desired, filing_status, other_income)
    std_ded = 16_100.0
    if filing_status == FilingStatus.married_jointly:
        std_ded = 32_200.0
    elif filing_status == FilingStatus.head_of_household:
        std_ded = 24_150.0

    tax_with = compute_tax(max(0, other_income + gross - std_ded), filing_status)
    tax_without = compute_tax(max(0, other_income - std_ded), filing_status)
    marginal_tax = tax_with - tax_without
    after_tax = gross - marginal_tax
    assert after_tax == pytest.approx(desired, abs=0.01)


def test_gross_up_200k_single() -> None:
    gross = gross_up_withdrawal(200_000, FilingStatus.single, 0)
    assert gross == pytest.approx(251_918.0, abs=1.0)
    _round_trip_verify(200_000, FilingStatus.single, 0)


def test_gross_up_round_trip_200k() -> None:
    _round_trip_verify(200_000, FilingStatus.single, 0)


def test_gross_up_with_other_income() -> None:
    gross = gross_up_withdrawal(50_000, FilingStatus.single, 50_000)
    assert gross > 50_000
    _round_trip_verify(50_000, FilingStatus.single, 50_000)


def test_gross_up_married_jointly_wider_brackets() -> None:
    gross_single = gross_up_withdrawal(100_000, FilingStatus.single, 0)
    gross_married = gross_up_withdrawal(100_000, FilingStatus.married_jointly, 0)
    # Married jointly has wider brackets → less tax → lower gross
    assert gross_married < gross_single
    _round_trip_verify(100_000, FilingStatus.married_jointly, 0)


def test_gross_up_other_income_equals_deduction() -> None:
    # Single deduction = $16,100. Other income = $16,100 → no deduction left.
    # $10K desired, first bracket at 10% → gross = 10,000 / 0.90 ≈ 11,111.11
    gross = gross_up_withdrawal(10_000, FilingStatus.single, 16_100)
    assert gross == pytest.approx(11_111.11, abs=1.0)
    _round_trip_verify(10_000, FilingStatus.single, 16_100)


def test_gross_up_partial_deduction() -> None:
    # Other income = $10,000 → deduction remaining = $6,100
    # $20K desired: $6,100 at 0% + rest at 10%
    gross = gross_up_withdrawal(20_000, FilingStatus.single, 10_000)
    _round_trip_verify(20_000, FilingStatus.single, 10_000)
    assert gross > 20_000


def test_gross_up_pathological_high_income() -> None:
    """Single filer, $500K other income, $1M desired spending.

    Other income already in 35% bracket. Withdrawal starts at 35%, hits 37%.
    """
    gross = gross_up_withdrawal(1_000_000, FilingStatus.single, 500_000)
    # Should need ~55-65% more than spending
    assert 1_500_000 < gross < 1_700_000
    _round_trip_verify(1_000_000, FilingStatus.single, 500_000)


def test_gross_up_head_of_household() -> None:
    _round_trip_verify(80_000, FilingStatus.head_of_household, 20_000)


def test_gross_up_married_separately() -> None:
    _round_trip_verify(60_000, FilingStatus.married_separately, 30_000)


# ---------------------------------------------------------------------------
# gross_up_withdrawal_array tests (vectorized)
# ---------------------------------------------------------------------------


def test_array_matches_scalar_single() -> None:
    """Vectorized results should match scalar for a range of values."""
    values = [0.0, 10_000.0, 50_000.0, 100_000.0, 200_000.0]
    arr = np.array(values)
    result = gross_up_withdrawal_array(arr, FilingStatus.single, 0.0)
    for i, v in enumerate(values):
        expected = gross_up_withdrawal(v, FilingStatus.single, 0.0)
        assert result[i] == pytest.approx(expected, abs=0.01)


def test_array_matches_scalar_with_other_income() -> None:
    values = [0.0, 20_000.0, 80_000.0]
    arr = np.array(values)
    result = gross_up_withdrawal_array(arr, FilingStatus.single, 50_000.0)
    for i, v in enumerate(values):
        expected = gross_up_withdrawal(v, FilingStatus.single, 50_000.0)
        assert result[i] == pytest.approx(expected, abs=0.01)


def test_array_2d_shape() -> None:
    arr = np.array([[50_000.0, 60_000.0], [70_000.0, 80_000.0]])
    result = gross_up_withdrawal_array(arr, FilingStatus.married_jointly, 0.0)
    assert result.shape == (2, 2)
    for i in range(2):
        for j in range(2):
            expected = gross_up_withdrawal(arr[i, j], FilingStatus.married_jointly, 0.0)
            assert result[i, j] == pytest.approx(expected, abs=0.01)


def test_array_all_zeros() -> None:
    arr = np.zeros((5, 3))
    result = gross_up_withdrawal_array(arr, FilingStatus.single, 0.0)
    assert np.all(result == 0.0)


def test_array_high_income() -> None:
    arr = np.array([1_000_000.0])
    result = gross_up_withdrawal_array(arr, FilingStatus.single, 500_000.0)
    expected = gross_up_withdrawal(1_000_000.0, FilingStatus.single, 500_000.0)
    assert result[0] == pytest.approx(expected, abs=0.01)
