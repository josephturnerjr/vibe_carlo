# Phase 3 — Architecture

## Overview
Phase 3 significantly expands the simulation engine's complexity. The web layer remains largely the same (FastAPI + HTMX), but the simulation module grows to handle tax logic, Social Security, RMDs, and multiple income streams. Scenario comparison requires storing and comparing multiple simulation configurations.

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                          Browser                              │
│                                                              │
│  ┌────────────┐ ┌──────────┐ ┌────────────┐ ┌────────────┐  │
│  │ Simulation  │ │Dashboard │ │ Scenario   │ │ Roth       │  │
│  │ Form        │ │          │ │ Comparison │ │ Conversion │  │
│  │ (expanded)  │ │          │ │ View       │ │ Analyzer   │  │
│  └─────────────┘ └──────────┘ └────────────┘ └────────────┘  │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                      FastAPI Server                           │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                  Simulation Engine (expanded)             │ │
│  │                                                          │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │ │
│  │  │ Market Model  │  │ Tax Engine   │  │ Social        │  │ │
│  │  │ (bootstrap)   │  │ (brackets,   │  │ Security      │  │ │
│  │  │               │  │  cap gains)  │  │ Estimator     │  │ │
│  │  └──────────────┘  └──────────────┘  └───────────────┘  │ │
│  │                                                          │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │ │
│  │  │ RMD          │  │ Income       │  │ Spending      │  │ │
│  │  │ Calculator   │  │ Streams      │  │ Rules         │  │ │
│  │  │              │  │              │  │ (guardrails)  │  │ │
│  │  └──────────────┘  └──────────────┘  └───────────────┘  │ │
│  │                                                          │ │
│  │  ┌──────────────────────────────────────────────────┐    │ │
│  │  │ Withdrawal Optimizer                              │    │ │
│  │  │ (tax-aware account ordering)                      │    │ │
│  │  └──────────────────────────────────────────────────┘    │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌──────────────────┐        ┌───────────────────────────┐  │
│  │ Scenario Service  │        │  SQLite                    │  │
│  │ (compare, diff)   │        │  + scenarios table         │  │
│  └──────────────────┘        └───────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

## Simulation Engine Expansion

The simulation engine evolves from a single function into a modular pipeline. Each simulated year processes these steps in order:

```
For each simulated year:
  1. Sample historical year (block bootstrap) → returns + inflation
  2. Compute income: salary + side income + pension + Social Security (if eligible)
  3. Compute RMDs (if applicable, age 73+)
  4. Determine spending (fixed, % of portfolio, or guardrails)
  5. Determine withdrawals needed: spending - income
  6. Optimize withdrawal order across accounts (tax-aware)
  7. Compute taxes on withdrawals + RMDs + income
  8. Apply investment returns per account (by allocation)
  9. Adjust for inflation
  10. Record portfolio state
```

## Key Design Decisions
- **Modular simulation pipeline**: Each financial component (tax, SS, RMD, spending rules) is a separate module that plugs into the year-by-year simulation loop. This keeps each piece testable and replaceable.
- **Scenario as a first-class entity**: A scenario is a named set of simulation parameters stored in the DB. Users can clone, modify, and compare scenarios.
- **Tax tables as data**: Federal and state tax brackets stored as configuration data (not hardcoded logic), making them easy to update annually.
