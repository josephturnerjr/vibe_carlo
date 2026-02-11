# Phase 4 — Architecture

## Overview
Phase 4 does not fundamentally change the architecture — it extends it. The simulation engine gains more financial modules (real estate, debt, goals). New services are added for reporting, API access, and payments. Performance optimization is applied to the existing simulation pipeline.

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                           Browser                                   │
│                                                                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │Simulation│ │Dashboard │ │Scenarios │ │Reports   │ │Account  │ │
│  │Form      │ │          │ │& Compare │ │& Export  │ │Settings │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └─────────┘ │
└────────────────────────────────┬───────────────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   Web Routes     │  │   REST API       │  │   Webhook /      │
│   (HTMX)        │  │   (/api/v1/...)  │  │   Stripe Events  │
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                     │                     │
         ▼                     ▼                     ▼
┌──────────────────────────────────────────────────────────────────┐
│                        FastAPI Server                             │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                 Simulation Engine                           │  │
│  │  ┌────────┐ ┌─────┐ ┌─────┐ ┌────────┐ ┌──────────────┐  │  │
│  │  │Market  │ │Tax  │ │SS   │ │RMD     │ │Real Estate   │  │  │
│  │  │Model   │ │     │ │     │ │        │ │              │  │  │
│  │  └────────┘ └─────┘ └─────┘ └────────┘ └──────────────┘  │  │
│  │  ┌────────┐ ┌─────────┐ ┌──────────┐ ┌──────────────┐    │  │
│  │  │Income  │ │Spending │ │Withdrawal│ │Debt          │    │  │
│  │  │Streams │ │Rules    │ │Optimizer │ │Model         │    │  │
│  │  └────────┘ └─────────┘ └──────────┘ └──────────────┘    │  │
│  │  ┌──────────────────────────────────────────────────┐     │  │
│  │  │ Goals Engine (education, purchases, legacy)       │     │  │
│  │  └──────────────────────────────────────────────────┘     │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐ │
│  │ Report       │ │ Payment      │ │ API Key                  │ │
│  │ Generator    │ │ Service      │ │ Management               │ │
│  │ (PDF/CSV)    │ │ (Stripe)     │ │                          │ │
│  └──────────────┘ └──────────────┘ └──────────────────────────┘ │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              SQLAlchemy ORM                                │   │
│  │  Tables: users, snapshots, accounts, scenarios,           │   │
│  │          goals, debts, api_keys, subscriptions            │   │
│  └────────────────────────────┬──────────────────────────────┘   │
└───────────────────────────────┼──────────────────────────────────┘
                                │
                         ┌──────▼──────┐
                         │  SQLite DB   │
                         │ (or Postgres │
                         │  if needed)  │
                         └─────────────┘
```

## Key Design Decisions
- **REST API alongside web routes**: The same simulation service powers both the HTMX web UI and the API. API routes are versioned (`/api/v1/`) and return JSON.
- **Report generation**: PDF via a Python library (e.g., `weasyprint` or `reportlab`). CSV export is straightforward.
- **Stripe for payments**: Industry standard, handles PCI compliance. Webhook endpoint for subscription events.
- **Performance**: Numba JIT on the simulation inner loop. Result caching keyed on input hash. These are targeted optimizations, not architectural changes.
- **PostgreSQL migration**: Only if SQLite write contention becomes an issue with concurrent users. SQLite handles reads well; writes are serialized but fast for small payloads.
