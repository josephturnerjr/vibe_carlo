# Phase 1 — MVP Product Specification

## Goal
A stateless web tool where anyone can input basic financial details and immediately see a Monte Carlo projection of their financial future. No accounts, no persistence, no login.

## User Inputs
- Current portfolio value ($)
- Annual contributions ($)
- Annual spending / withdrawal ($)
- Current age
- Expected retirement age
- Planning horizon end age (e.g., 90)
- Asset allocation: stocks/bonds percentage split

## Simulation
- 10,000 Monte Carlo runs per request
- Block bootstrap resampling from historical data: for each simulated year, a single historical year is drawn at random (with replacement), and that year's stock return, bond return, and inflation rate are used together — preserving cross-asset and asset-inflation correlations
- Portfolio compounds year-by-year: apply weighted return (per allocation), subtract spending, add contributions, adjust for inflation
- All outputs in real (inflation-adjusted) dollars

## Historical Data
- Unified CSV shipped in the repo: S&P 500 total returns, US bond returns, CPI inflation (1928–present)
- Sources: Damodaran (NYU Stern) or Shiller datasets
- No external API dependencies at runtime

## Outputs / Visualizations
- **Fan chart**: percentile bands (10th, 25th, 50th, 75th, 90th) of portfolio value over time
- **Success probability**: percentage of simulations where the portfolio survives to the end of the planning horizon
- **Distribution histogram**: portfolio value distribution at a user-selected future year

## What Phase 1 Does NOT Include
- User accounts or authentication
- Saving or persisting simulation results
- Back-testing against previous projections
- Multiple account types (401k, IRA, brokerage, etc.)
- Tax modeling
- Social Security, RMDs, or other advanced financial features
