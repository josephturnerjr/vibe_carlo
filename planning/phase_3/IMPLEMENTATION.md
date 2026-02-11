# Phase 3 — Implementation Plan

## Overview
Phase 3 is primarily a simulation engine expansion. The web layer gains new pages (scenario comparison, Roth analyzer) but the core architectural change is making the simulation pipeline modular enough to incorporate tax, Social Security, RMDs, and flexible spending rules.

## Implementation Steps

### 1. Modular Simulation Pipeline
- Refactor `engine.py` from a single function into a pipeline of composable steps
- Each step is a separate module: `tax.py`, `social_security.py`, `rmd.py`, `income.py`, `spending.py`, `withdrawal.py`
- The engine orchestrates the steps in order for each simulated year
- Each module is independently testable

### 2. Tax Engine (`simulation/tax.py`)
- Load federal tax brackets from a data file (JSON or TOML)
- Compute federal income tax on: salary, traditional account withdrawals, RMDs
- Capital gains tax on brokerage withdrawals (assume long-term for simplicity; short-term as future enhancement)
- State tax: user-provided flat rate or state selection (load state brackets from data)
- Standard deduction applied

### 3. Social Security Estimator (`simulation/social_security.py`)
- Simplified PIA (Primary Insurance Amount) estimate based on user inputs
- Model claiming at different ages with actuarial adjustments (62: ~70%, 67: 100%, 70: ~124%)
- Integrate as income stream starting at claiming age
- Annual COLA adjustments tied to simulated inflation

### 4. RMD Calculator (`simulation/rmd.py`)
- IRS Uniform Lifetime Table (hardcoded as data)
- Calculate RMD for each tax-deferred account based on prior year-end balance and age
- Force distribution as taxable income
- Excess over spending needs gets reinvested in taxable account

### 5. Income Streams (`simulation/income.py`)
- Salary: fixed amount with annual growth rate, ends at retirement age
- Side income: amount with start/end age
- Pension: fixed or inflation-adjusted amount with start age

### 6. Spending Rules (`simulation/spending.py`)
- Fixed real spending (existing behavior)
- Percentage of portfolio (e.g., 4% rule)
- Guardrails: base spending ± adjustments when portfolio crosses thresholds
- Floor and ceiling on spending

### 7. Withdrawal Optimizer (`simulation/withdrawal.py`)
- Determine how much to withdraw and from which accounts
- Default ordering: taxable first, then tax-deferred, then Roth (tax-efficient)
- Respect RMD minimums from tax-deferred accounts
- User can override ordering

### 8. Roth Conversion Analyzer
- New page: model converting $X/year from traditional to Roth during specified years
- Show tax cost of conversion in simulation
- Compare scenarios: with and without conversion
- Break-even analysis across percentiles

### 9. Scenario Comparison
- New DB table: `scenarios` (user_id, name, parameters JSON)
- Clone/modify scenarios
- Side-by-side fan chart view (2-3 scenarios)
- Difference chart: percentile-by-percentile comparison

### 10. Tax Data Management
- Federal brackets, state brackets, standard deduction as versioned data files
- Easy to update annually when new tax tables are published
- Consider a management command or script to update tax data

## Testing
- Each simulation module gets its own test file with deterministic, seeded tests
- Tax calculations tested against known IRS examples
- RMD calculations tested against IRS worksheet examples
- Social Security estimates tested against SSA quick calculator results
- Integration tests: full pipeline with all modules active
