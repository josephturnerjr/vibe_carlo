# Phase 3 — Advanced Financial Modeling Product Specification

## Goal
Sophisticated enough to be a real planning tool for people approaching or in retirement. Adds tax awareness, Social Security, retirement-specific rules, and scenario comparison.

## Features

### Tax Modeling
- Federal income tax brackets (applied to withdrawals from tax-deferred accounts)
- Capital gains tax (short-term vs. long-term) on brokerage account withdrawals
- State income tax (user selects state or enters a flat rate)
- Tax-aware withdrawal ordering (which accounts to draw from first)

### Social Security
- Estimated benefit based on user-provided inputs (current salary, years worked, claiming age)
- Model different claiming ages (62, 67, 70) and their impact on projections
- Integrated into simulation as an income stream starting at claiming age

### Required Minimum Distributions (RMDs)
- Automatic RMD calculation for traditional IRA/401(k) accounts starting at age 73+
- RMDs treated as taxable income in the simulation
- Uses IRS Uniform Lifetime Table

### Roth Conversion Analysis
- Model converting traditional IRA/401(k) dollars to Roth
- Simulate the tax cost of conversion vs. long-term tax-free growth benefit
- Show break-even analysis across simulation percentiles

### Income Modeling
- Salary with configurable annual growth rate
- Side income / freelance (with start/end ages)
- Pension income (fixed or inflation-adjusted, with start age)

### Scenario Comparison
- Save multiple "what-if" scenarios (e.g., retire at 60 vs. 65, different spending levels)
- Side-by-side fan chart comparison
- Difference view: how much better/worse is scenario A vs. B at each percentile

### Variable Spending Rules
- Guardrails strategy: increase spending when portfolio exceeds upper threshold, decrease when below lower threshold
- Percentage-of-portfolio spending (e.g., 4% rule with floor/ceiling)
- Fixed real spending (current default)
