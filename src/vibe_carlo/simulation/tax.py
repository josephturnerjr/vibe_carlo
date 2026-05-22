"""Federal income tax computation for retirement withdrawal gross-up.

Uses 2026 tax brackets and standard deductions per IRS inflation adjustments.
All withdrawals assumed to be ordinary income (traditional IRA/401k).
"""

import numpy as np
import numpy.typing as npt

from vibe_carlo.schemas import FilingStatus

# 2026 federal tax rates (progressive brackets)
RATES: list[float] = [0.10, 0.12, 0.22, 0.24, 0.32, 0.35, 0.37]

# Bracket upper bounds (taxable income) by filing status.
# Each list has 7 entries; the last is effectively infinity.
_INF = float("inf")

BRACKETS: dict[FilingStatus, list[float]] = {
    FilingStatus.single: [12_400, 50_400, 105_700, 201_775, 256_225, 640_600, _INF],
    FilingStatus.married_jointly: [
        24_800,
        100_800,
        211_400,
        403_550,
        512_450,
        768_700,
        _INF,
    ],
    FilingStatus.married_separately: [
        12_400,
        50_400,
        105_700,
        201_775,
        256_225,
        384_350,
        _INF,
    ],
    FilingStatus.head_of_household: [
        17_700,
        67_450,
        105_700,
        201_750,
        256_200,
        640_600,
        _INF,
    ],
}

STANDARD_DEDUCTION: dict[FilingStatus, float] = {
    FilingStatus.single: 16_100.0,
    FilingStatus.married_jointly: 32_200.0,
    FilingStatus.married_separately: 16_100.0,
    FilingStatus.head_of_household: 24_150.0,
}


def gross_up_withdrawal_array(
    desired_spending: npt.NDArray[np.float64],
    filing_status: FilingStatus,
) -> npt.NDArray[np.float64]:
    """Vectorized gross-up: compute pre-tax withdrawal yielding desired_spending after tax.

    Assumes the withdrawal is the filer's only income (earnings are post-tax and
    handled separately). For each element W in the output, W - tax(W) equals the
    corresponding desired_spending entry.

    Algorithm (exact, analytical, O(7)):
    1. Fill the standard deduction at 0% rate, then walk brackets.
    2. Each $1 gross at rate r yields $(1-r) after-tax.
    """
    std_ded = STANDARD_DEDUCTION[filing_status]
    brackets = BRACKETS[filing_status]

    after_tax_remaining = desired_spending.copy()
    gross = np.zeros_like(desired_spending)

    # Phase 1: consume standard deduction (tax-free)
    if std_ded > 0:
        use = np.minimum(std_ded, after_tax_remaining)
        use = np.maximum(use, 0.0)
        gross += use
        after_tax_remaining -= use

    # Phase 2: walk brackets
    prev_bound = 0.0
    for rate, upper in zip(RATES, brackets):
        bracket_capacity = upper - prev_bound

        after_tax_per_dollar = 1.0 - rate
        after_tax_capacity = bracket_capacity * after_tax_per_dollar

        can_fill = np.minimum(after_tax_remaining, after_tax_capacity)
        can_fill = np.maximum(can_fill, 0.0)

        gross += can_fill / after_tax_per_dollar
        after_tax_remaining -= can_fill

        prev_bound = upper

    return gross
