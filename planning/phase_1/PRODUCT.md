# Phase 1 — MVP Product Specification

## Goal
A stateless web tool where anyone can input basic financial details and immediately see a Monte Carlo projection of their financial future. No accounts, no persistence, no login.

## User Inputs
- Current portfolio value ($), broken down by Cash, Market, and Bonds
- Annual contributions ($) — in real (inflation-adjusted) terms
- Annual spending / withdrawal ($) — in real (inflation-adjusted) terms
- Years of simulation to run
- Advanced settings (hidden by default)
  - Sample years (default should be the years of simulation)

## Simulation
- 10,000 Monte Carlo runs per request
- Block bootstrap resampling from historical data: for each simulation, pick a random start index within the historical dataset such that the full block of length `Sample years` fits (i.e., clamp the start range so start + block_length ≤ dataset_length). Take that contiguous block of years' stock return, bond return, and inflation rate together — preserving cross-asset and asset-inflation correlations. If, after running a `Sample years` length block, there are more years to simulate, draw another block the same way and append it. Continue until all `Years of simulation to run` years have been simulated.
- Cash earns 0% real return (no historical data needed for cash)
- Portfolio compounds year-by-year: apply weighted return (per allocation), subtract spending, add contributions, adjust for inflation
- All outputs in real (inflation-adjusted) dollars

## Historical Data
- Unified CSV shipped in the repo: S&P 500 total returns, US bond returns, CPI inflation (1928–present)
- Sources: Damodaran (NYU Stern) or Shiller datasets
- No external API dependencies at runtime

## Outputs / Visualizations
- **Fan chart**: percentile bands (10th, 25th, 50th, 75th, 90th) of portfolio value over time
- **Success probability**: percentage of simulations where the portfolio never reaches $0 at any point during the simulation
- **Distribution histogram**: portfolio value distribution at the final simulated year

## What Phase 1 Does NOT Include
- User accounts or authentication
- Saving or persisting simulation results
- Back-testing against previous projections
- Multiple account types (401k, IRA, brokerage, etc.)
- Tax modeling
- Social Security, RMDs, or other advanced financial features
