# Phase 1 — Implementation Plan

## Technology Choices

| Component | Technology | Version/Notes |
|-----------|-----------|---------------|
| Language | Python 3.12+ | Modern typing syntax (`X | None`) |
| Package manager | uv | Fast, replaces pip/pip-tools |
| Web framework | FastAPI | With Jinja2Templates for server rendering |
| Validation | Pydantic v2 | Input/output schemas, via FastAPI |
| Simulation | NumPy | Vectorized Monte Carlo |
| Templates | Jinja2 | Server-rendered HTML |
| Interactivity | HTMX | Partial page swaps, no SPA |
| Charts | Plotly.js (via CDN) | Client-side interactive charts |
| CSS | Tailwind CSS (via CDN) | Utility-first styling |
| Testing | pytest | With FastAPI TestClient |
| Type checking | ty | Must pass cleanly before each commit |
| Formatting | ruff format | Must pass cleanly before each commit |
| Linting | ruff check | Must pass cleanly before each commit |
| Container | Docker | Dockerfile with uvicorn |
| Deployment | VPS + Caddy | Docker container behind Caddy reverse proxy |

## Implementation Steps

### 1. Project Scaffolding
- Initialize git repo
- Create `pyproject.toml` with dependencies: `fastapi`, `uvicorn`, `jinja2`, `numpy`, `python-multipart` (for form data)
- Dev dependencies: `pytest`, `httpx` (for TestClient), `ruff`, `ty`
- Set up `src/vibe_carlo/` package structure
- Configure `ruff` in `pyproject.toml` (target Python 3.12+)

### 2. Historical Data
- Obtain historical returns data (Damodaran dataset preferred — publicly available at NYU Stern)
- Create `src/vibe_carlo/data/historical_returns.csv` with columns: `year`, `sp500_return`, `bond_return`, `cpi_inflation`
- All returns as decimals (e.g., 0.10 for 10%)
- Write data loading function in `simulation/models.py` that reads CSV into NumPy array at module import time

### 3. Simulation Engine (`simulation/engine.py`)
- Core function: `run_simulation(params: SimulationParams, historical_data: np.ndarray, n_runs: int = 10_000, seed: int | None = None) -> SimulationResult`
- Block bootstrap: for each run, sample `n_years` row indices from historical data (with replacement), pull stock return, bond return, and inflation for each
- Compute blended portfolio return per year: `allocation * stock_return + (1 - allocation) * bond_return`
- Compound year-by-year: apply return, subtract spending, add contributions, adjust for inflation
- Portfolio floor at $0 (can't go negative)
- Return percentile time series (10th, 25th, 50th, 75th, 90th) and success rate
- All operations vectorized with NumPy (simulate all 10,000 runs as a 2D array)

### 4. Pydantic Schemas (`schemas.py`)
- `SimulationInput`: portfolio_value, annual_contribution, annual_spending, current_age, retirement_age, end_age, stock_allocation (0.0–1.0)
- `SimulationOutput`: percentiles dict, success_rate, year_labels, metadata
- Input validation: all values non-negative, ages make sense (current < retirement ≤ end), allocation between 0 and 1

### 5. FastAPI App (`app.py`)
- `GET /` → render `index.html` (input form)
- `POST /simulate` → validate input, run simulation, render `partials/results.html`
- Mount static files directory
- Load historical data at startup (app lifespan event)

### 6. Templates
- `base.html`: HTML boilerplate, CDN links for HTMX, Plotly.js, Tailwind CSS
- `index.html`: Input form with HTMX attributes (`hx-post="/simulate"`, `hx-target="#results"`, `hx-swap="innerHTML"`)
- `partials/results.html`: Fan chart, histogram, and success rate display. Chart data embedded as JSON in a `<script>` tag that Plotly.js reads.

### 7. Dockerfile
- Base: `python:3.12-slim`
- Install `uv`, copy project, install dependencies
- Run with `uvicorn vibe_carlo.app:app --host 0.0.0.0 --port 8000`

### 8. Tests
- `test_engine.py`: Deterministic tests with seeded RNG — verify output shape, percentile ordering (10th < 25th < 50th < ...), success rate bounds, edge cases (zero portfolio, 100% bonds, etc.)
- `test_api.py`: Integration tests via FastAPI TestClient — verify form renders, POST returns 200 with results, validation errors return appropriate responses

## Deployment
- Build Docker image
- Deploy to existing VPS
- Add Caddy config block for the domain:
  ```
  vibe-carlo.example.com {
      reverse_proxy localhost:8000
  }
  ```
- Caddy handles TLS automatically via Let's Encrypt

## Performance Considerations
- 10,000 runs × ~30 years = ~300,000 operations per simulation — NumPy handles this in milliseconds
- Historical data loaded once at startup (~100 rows), negligible memory
- No database queries, no I/O during simulation — pure compute
- If needed later: add request timeout, rate limiting via middleware
