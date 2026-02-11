# Phase 2 — Implementation Plan

## New Dependencies
- `sqlalchemy` — ORM
- `alembic` — database migrations
- `aiosqlite` — async SQLite driver for SQLAlchemy
- Auth library (TBD: evaluate `fastapi-users`, `authlib`, or custom)
- `argon2-cffi` — password hashing (if custom auth)
- `itsdangerous` — session signing

## Implementation Steps

### 1. Database Setup
- Add SQLAlchemy models for `users`, `snapshots`, `accounts`
- Configure async SQLAlchemy engine with SQLite
- Set up Alembic for migrations
- Create initial migration

### 2. Authentication
- Evaluate auth approach: `fastapi-users` (batteries-included) vs. custom (more control)
- Implement: registration, login, logout, password reset
- Session middleware with secure, httponly, samesite cookies
- CSRF protection on all form POSTs
- Protected routes (dashboard, snapshots) require login
- Simulation page remains accessible without login

### 3. Snapshot Storage
- After simulation, offer "Save Snapshot" button (requires login)
- Store inputs as JSON, store computed outputs as JSON
- Snapshot list view on dashboard, sorted by date
- "Re-run" button to load a snapshot's inputs into the simulation form

### 4. Back-Testing
- When saving a new snapshot, optionally enter current actual portfolio value
- Back-test view: select a previous snapshot, overlay actual value on its fan chart
- Compute which percentile band the actual value falls in
- Show trajectory: line connecting actual values across snapshots over time

### 5. Multiple Account Types
- UI for managing financial accounts (add/edit/delete)
- Each account has: name, type, balance, contribution, allocation
- Simulation aggregates across all accounts
- Per-account results breakdown in output

### 6. Expanded Asset Classes
- Update `historical_returns.csv` with additional columns (international stocks, cash)
- Update simulation engine to handle N asset classes with per-account allocations
- Weighted return calculation becomes a dot product of allocation vector and returns vector

### 7. Deployment Updates
- Add Docker volume mount for SQLite DB in `docker-compose.yml`
- Add backup script (cron job to copy SQLite file to a backup location)
- Enforce HTTPS redirects (Caddy handles this)

## Security Additions
- Password hashing with Argon2
- CSRF tokens on all forms
- Rate limiting on auth endpoints (prevent brute force)
- Content Security Policy headers
- Input sanitization (Jinja2 autoescaping already handles most XSS)
- Parameterized queries via SQLAlchemy (prevents SQL injection)
