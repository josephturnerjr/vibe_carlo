# Phase 2 — Architecture

## Overview
Phase 2 adds persistence and user identity. The stateless simulation engine from Phase 1 remains unchanged, but is now wrapped with authentication, a database for storing snapshots, and a dashboard for viewing history and back-test results.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                        Browser                           │
│                                                         │
│  ┌────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Input Form  │  │  Dashboard   │  │  Back-test     │  │
│  │ (HTMX)     │  │  (snapshots) │  │  Overlay View  │  │
│  └─────┬──────┘  └──────┬───────┘  └───────┬────────┘  │
└────────┼────────────────┼───────────────────┼───────────┘
         │                │                   │
         ▼                ▼                   ▼
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Server                        │
│                                                         │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Auth     │  │  Simulation  │  │  Snapshot        │  │
│  │  Middleware│  │  Routes      │  │  Routes          │  │
│  └──────┬───┘  └──────┬───────┘  └──────┬───────────┘  │
│         │             │                  │              │
│         ▼             ▼                  ▼              │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Session  │  │  Simulation  │  │  Snapshot        │  │
│  │  Store    │  │  Engine      │  │  Service         │  │
│  └──────┬───┘  │  (NumPy)     │  │  (save/load/     │  │
│         │      └──────────────┘  │   compare)        │  │
│         │                        └──────┬───────────┘  │
│         ▼                               ▼              │
│  ┌─────────────────────────────────────────────────┐   │
│  │              SQLAlchemy ORM                       │   │
│  │                                                   │   │
│  │  Tables: users, snapshots, accounts               │   │
│  └───────────────────────┬───────────────────────────┘   │
│                          │                               │
└──────────────────────────┼───────────────────────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   SQLite DB   │
                    │  (Docker vol) │
                    └──────────────┘
```

## Data Model

```
users
├── id (UUID)
├── email
├── password_hash
├── created_at

snapshots
├── id (UUID)
├── user_id (FK → users)
├── name
├── created_at
├── inputs (JSON — all simulation parameters)
├── outputs (JSON — percentiles, success rate)
├── actual_portfolio_value (nullable — for back-testing)

accounts (financial accounts, not user accounts)
├── id (UUID)
├── user_id (FK → users)
├── name (e.g., "401k", "Roth IRA")
├── account_type (enum: brokerage, 401k, ira, roth_ira, savings)
├── balance
├── annual_contribution
├── stock_allocation
```

## Key Design Decisions
- **SQLite in a Docker volume**: Simple, no separate database server. The DB file persists across container restarts via a mounted volume. Automated backups via cron copying the file.
- **JSON columns for snapshot data**: Simulation inputs and outputs are stored as JSON blobs. This avoids rigid schema changes as the simulation model evolves across phases.
- **Session-based auth**: Secure httponly cookies. No JWT complexity needed for a server-rendered app.
- **SQLAlchemy + Alembic**: ORM for clean data access, Alembic for schema migrations as the model grows.
