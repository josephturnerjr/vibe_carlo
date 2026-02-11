# Phase 2 — Persistence & Accounts Product Specification

## Goal
Users can create accounts, save simulation snapshots, and track how their financial projections evolve over time. Introduces back-testing: comparing current reality against previous projections.

## Features

### User Accounts
- Registration (email + password)
- Login / logout
- Password reset
- Account deletion (with all associated data)

### Snapshots
- Each simulation run can be saved as a named "snapshot"
- A snapshot stores: all input parameters, full simulation output (percentiles, success rate), and a timestamp
- Users can view a list of all their snapshots
- Users can re-run any previous snapshot's inputs to see updated projections

### Back-Testing
- When creating a new snapshot, users enter their current actual portfolio value
- The system overlays the actual value on previous projection fan charts
- Shows whether reality is tracking the median, pessimistic, or optimistic scenarios
- Simple accuracy metric: which percentile band does reality fall in?

### Multiple Account Types
- Model financial accounts separately: brokerage, 401(k), IRA, Roth IRA, savings
- Each account has its own balance and contribution schedule
- Asset allocation can vary per account
- Simulation runs across all accounts with combined results

### Improved Asset Allocation
- Expand beyond stocks/bonds to include: US stocks, international stocks, bonds, cash/money market
- Historical data table expanded with additional asset class columns

## What Phase 2 Does NOT Include
- Tax modeling
- Social Security or RMDs
- Roth conversion analysis
- Scenario comparison (what-if)
- Variable spending rules
