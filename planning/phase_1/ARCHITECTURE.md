# Phase 1 — Architecture

## Overview
Phase 1 is a stateless request/response application. The browser sends form inputs to the server, the server runs the simulation, and returns rendered HTML (with embedded chart data) back to the browser. No database, no background jobs, no auth.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│                      Browser                         │
│                                                     │
│  ┌──────────────┐         ┌──────────────────────┐  │
│  │  Input Form   │         │  Plotly.js Charts     │  │
│  │  (HTMX POST)  │────────▶│  (fan chart, hist,   │  │
│  │               │  swap   │   success %)          │  │
│  └──────────────┘         └──────────────────────┘  │
│         │                          ▲                 │
│         │ POST /simulate           │ HTML partial    │
│         │ (form data)              │ + JSON chart    │
└─────────┼──────────────────────────┼─────────────────┘
          │                          │
          ▼                          │
┌─────────────────────────────────────────────────────┐
│                   FastAPI Server                     │
│                                                     │
│  ┌──────────────┐   ┌──────────────┐                │
│  │  Routes       │──▶│  Schemas     │                │
│  │  (app.py)     │   │  (Pydantic)  │                │
│  └──────┬───────┘   └──────────────┘                │
│         │                                           │
│         ▼                                           │
│  ┌──────────────────────────────────┐               │
│  │  Simulation Engine               │               │
│  │  (engine.py)                     │               │
│  │                                  │               │
│  │  ┌────────────────────────────┐  │               │
│  │  │ historical_returns.csv     │  │               │
│  │  │ (loaded once at startup)   │  │               │
│  │  └────────────────────────────┘  │               │
│  │                                  │               │
│  │  NumPy vectorized simulation:    │               │
│  │  - Sample N historical years     │               │
│  │  - Apply returns + inflation     │               │
│  │  - Compute percentiles           │               │
│  └──────────────────────────────────┘               │
│         │                                           │
│         ▼                                           │
│  ┌──────────────┐                                   │
│  │  Jinja2       │──▶ HTML partial (results.html)   │
│  │  Templates    │    with embedded Plotly JSON      │
│  └──────────────┘                                   │
└─────────────────────────────────────────────────────┘
```

## Request Flow
1. User fills out the input form on `index.html`
2. HTMX intercepts the form submit and POSTs to `/simulate`
3. FastAPI validates inputs via Pydantic schema
4. Simulation engine runs 10,000 Monte Carlo paths (vectorized NumPy)
5. Engine returns percentile time series + summary statistics
6. Route renders `partials/results.html` with chart data embedded as JSON
7. HTMX swaps the results partial into the page
8. Plotly.js renders interactive charts client-side

## Key Design Decisions
- **Stateless**: No database, no sessions. Every request is independent. This simplifies deployment and eliminates data security concerns for Phase 1.
- **Server-side simulation**: NumPy is fast enough for 10,000 runs with annual steps (~30 years × 10,000 = 300,000 operations). No need for client-side compute.
- **HTMX partial swap**: The form posts and only the results area updates — no full page reload, no SPA complexity.
- **Historical data loaded at startup**: The CSV is read into a NumPy array once when the app starts, not on every request.

## Project Structure
```
vibe_carlo/
├── pyproject.toml
├── Dockerfile
├── README.md
├── CLAUDE.md
├── planning/
├── src/
│   └── vibe_carlo/
│       ├── __init__.py
│       ├── app.py              # FastAPI app, routes
│       ├── data/
│       │   └── historical_returns.csv
│       ├── simulation/
│       │   ├── __init__.py
│       │   ├── engine.py       # Monte Carlo simulation core
│       │   └── models.py       # Data loading, financial model parameters
│       ├── schemas.py          # Pydantic input/output schemas
│       ├── templates/
│       │   ├── base.html
│       │   ├── index.html
│       │   └── partials/
│       │       └── results.html
│       └── static/
│           └── css/
│               └── custom.css
└── tests/
    ├── test_engine.py
    └── test_api.py
```
