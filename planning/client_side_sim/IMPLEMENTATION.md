# Implementation Plan — Client-side Monte Carlo Simulation Page

This plan is the minimum work needed to satisfy SPEC.md given the architecture in ARCH.md and the test plan in TEST.md. It assumes those three files have been read.

The work is broken into seven steps that should be executed in order. Each step is small and independently verifiable.

## Step 1 — Server: cache historical data as JSON at startup

**File:** `src/vibe_carlo/app.py`

- In the `lifespan()` function, after `historical_data = load_historical_data()`, also compute and cache a JSON-serialized copy:
  ```python
  global historical_data, historical_data_json  # noqa: PLW0603
  historical_data = load_historical_data()
  historical_data_json = json.dumps(historical_data.tolist())
  ```
- Add `historical_data_json: str` module-level annotation alongside the existing `historical_data` annotation.
- This is a one-time cost at startup; the JSON is reused on every public-page render.

## Step 2 — Server: bifurcate `GET /`

**File:** `src/vibe_carlo/app.py`

Replace the current `index()` body. New behavior:

```python
@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    snapshot_id: int | None = Query(default=None),
) -> Response:
    user = _get_current_user(request)
    if user is None:
        return templates.TemplateResponse(
            request,
            "public_index.html",
            {"historical_data_json": historical_data_json},
        )
    # ... existing authed logic, unchanged ...
```

The `?snapshot_id=` query param continues to work for authenticated users; for unauthenticated users it's silently ignored (deep-link sharing isn't in scope).

## Step 3 — Template: `public_index.html`

**File (new):** `src/vibe_carlo/templates/public_index.html`

- Extends `base.html` (so it inherits Tailwind, Plotly, htmx, distribution_picker.js, custom.css).
- Imports the `distribution_picker` macro from `partials/distribution_picker.html`.
- **Form fields** (matching the authenticated page's defaults so the page is useful out-of-the-box):
  - `cash_value` (default `300000`), `market_value` (`2000000`), `bond_value` (`0`)
  - `earnings` (`400000`)
  - Spending picker: `truncated_normal`, `low=55000, high=100000, mean=74000, stddev=5000`
  - `filing_status` dropdown with same five options, default `single`
  - `years_to_simulate` (default `30`)
  - **Omit:** `sample_years` (advanced setting), all snapshot UI
- **Header / Login link**: rather than fork `base.html`, edit its `{% if user_email %}…{% endif %}` block to add an `{% else %}` arm that renders a single `Login` link in both the desktop nav and mobile nav. (See Step 4.)
- **Form submit**: do NOT use `hx-post`. Instead, the form has `id="sim-form"` and an inline `<script>` at the bottom of the template wires a `submit` event listener that calls `runClientSimulation(form)` from the new JS module.
- **Progress / Stop UI**: a `<div id="sim-progress">` that holds the live "X of 10,000 runs completed" text. The submit button toggles between two states:
  - Idle: `<button id="sim-button" type="submit">Run Simulation</button>`
  - Running: same button, text replaced with "Stop", click handler swapped to call the abort function.
  - When the run finishes (completed or stopped), revert.
- **Results container**: `<div id="results"></div>` — same id as authed page so the rendering shape is identical.
- **Inlined data**: at the bottom of the page,
  ```html
  <script type="application/json" id="historical-data">{{ historical_data_json | safe }}</script>
  ```

## Step 4 — Template: tweak `base.html` to show a Login link when logged out

**File:** `src/vibe_carlo/templates/base.html`

- Inside the existing `<header>`, the desktop nav and mobile nav are both gated by `{% if user_email %}`. Add an `{% else %}` arm to each that renders `<a href="/login">Login</a>` styled the same as the existing nav links.
- This is the only edit to `base.html`. No structural change.

## Step 5 — Client: pure simulation module

**File (new):** `src/vibe_carlo/static/js/client_sim.js`

A single ES-module-friendly file (loaded as `<script type="module">` from `public_index.html`). Exports both pure functions (for parity tests) and a top-level driver (for the page).

Pure-function exports — straight transliterations of the Python:
- `TAX_RATES`, `TAX_BRACKETS`, `STANDARD_DEDUCTION` — same constants as `simulation/tax.py`. Filing-status keys are the same string values used in Python (`"single"`, `"married_jointly"`, etc.).
- `grossUpWithdrawal(spending, filingStatus)` → number. Mirrors `gross_up_withdrawal`.
- `grossUpWithdrawalArray(spendingArr, filingStatus)` → `Float64Array`. Mirrors `gross_up_withdrawal_array`.
- `sampleFlat(value, nRuns, years)` → `Float64Array(nRuns * years)`.
- `sampleUniform(low, high, nRuns, years, rng)` → `Float64Array(nRuns * years)`.
- `sampleTruncatedNormal(low, high, mean, stddev, nRuns, years, rng)` — rejection sampling, same loop as `_sample_truncated_normal`.
- `sampleSpending(dist, nRuns, years, rng)` — dispatches to the three above based on `dist.dist_type`.
- `buildBootstrapIndices(rng, nRuns, years, blockLen, nHistorical)` → `Int32Array(nRuns * years)`. Mirrors `_build_bootstrap_indices` exactly: pick a random start in `[0, nHistorical-blockLen]`, walk `blockLen` consecutive indices, repeat until `years` are filled, with a partial trailing block when `years % blockLen != 0`.
- `runSimulationStep(state, batchStart, batchEnd, params, historicalData)` — does one batch of runs, mutating `state` (running portfolios array, ever-hit-zero count, final-year values).
- `computeResultsFromState(state, kCompleted, params)` → object matching `SimulationResult` shape (`year_labels`, `percentiles`, `success_rate`, `final_year_distribution`, `gross_withdrawal`, `effective_tax_rate`). Used both at the end of a full run and when Stop is pressed; with `k=0` it returns `null`.

A simple seedable PRNG is included (e.g. mulberry32 or splitmix32) — small, deterministic, lets parity tests inject a seed when needed. The page itself uses `Math.random` via the same wrapper interface.

Top-level driver export:
- `runClientSimulation(form, { onProgress, onComplete, onError, signal })`:
  1. Read form, build `params`. Validate (non-negative, total > 0, low ≤ high, mean within [low, high]); on failure call `onError` with a message and return.
  2. Parse `#historical-data` JSON once (cache on `window` so re-runs are free).
  3. Allocate `state` for `nRuns = 10000`, `batchSize = 500`.
  4. Loop `for (let i = 0; i < nRuns; i += batchSize)`:
     - Run `runSimulationStep(state, i, Math.min(i+batchSize, nRuns), params, data)`.
     - `onProgress(i + done)`.
     - `await new Promise(r => setTimeout(r, 0))` to yield to the event loop.
     - If `signal.aborted`, break.
  5. Call `computeResultsFromState(state, completed, params)` → call `onComplete(result, completed, nRuns)`.

## Step 6 — Client: page-level UI glue (inline `<script>` in `public_index.html`)

Kept inline in the template (not a separate file) because it's tightly coupled to the template's DOM ids and is small (~60 lines). It does:

- Imports `runClientSimulation` from `/static/js/client_sim.js`.
- Wires the form `submit` listener.
- Manages the Run/Stop button toggle and the progress text.
- Holds an `AbortController`; passes `controller.signal` to `runClientSimulation`.
- On `onProgress(k)`: updates `#sim-progress` to `${k.toLocaleString()} of 10,000 runs completed`.
- On `onComplete(result, completed, nRuns)`:
  - If `completed < nRuns`, set the progress text to `Stopped at ${completed.toLocaleString()} / ${nRuns.toLocaleString()} runs` and apply a `text-yellow-700` class.
  - Render the results into `#results` by building the same DOM structure as `partials/results.html` (success-rate card, optional tax-adjustment card, fan chart container, histogram container) with template literals.
  - Call the existing chart-rendering code (the same Plotly invocations used in `index.html`'s `renderCharts()`, factored into a small helper).
- On `onError(msg)`: render a red error message into `#results`.

To avoid duplicating the chart-rendering logic between `index.html` and `public_index.html`, the Plotly traces/layout factory functions are extracted into a small `static/js/charts.js` helper that both pages can include. (The server-side `index.html` already inlines them in a `<script>`; they move into the helper and both pages call into it.)

## Step 7 — Tests

Create the test files described in TEST.md.

**`tests/test_public_index.py`** — 13 tests covering server bifurcation, inlined-data correctness, and UI element presence/absence. Uses the existing `client` / `db_path` fixtures from `conftest.py` (and the `authed_client` fixture pattern used in `test_snapshot_api.py`).

**`tests/test_client_sim_parity.py`** — ~28 tests invoking Node via `subprocess.run`. Helpers:
- `_run_node(js_module_path, function_name, args_json) -> dict | list | float` — shells out, returns parsed JSON.
- A pytest fixture `node_available` that runs `node --version` once and uses `pytest.skip` when Node isn't on `PATH`.
- For end-to-end engine parity tests, both Python and JS take the same pre-computed bootstrap indices and spending samples, eliminating PRNG differences.

## Order of work / verification at each step

1. Steps 1 + 2 + 4 (server-side bifurcation + base.html Login link) → write `tests/test_public_index.py` tests #1, #2, #3, #7, #10. Run `uv run pytest tests/test_public_index.py`.
2. Step 3 (template) → tests #4, #5, #6, #8, #9, #11, #12 pass.
3. Step 5 (pure JS module) → write `tests/test_client_sim_parity.py` tests #14–#30. Run with `uv run pytest tests/test_client_sim_parity.py`. (Skips for contributors without Node.)
4. Step 5 cont. (engine + percentile / partial-results functions) → tests #31–#41 pass.
5. Step 6 (UI glue) → manual smoke checklist from TEST.md. Verify with browser DevTools that no XHR fires during a run.
6. Pre-commit: `uv run ruff format . && uv run ruff check . && uv run ty check && uv run pytest`.
7. Commit.

## Files changed / added (final list)

**Added:**
- `src/vibe_carlo/templates/public_index.html`
- `src/vibe_carlo/static/js/client_sim.js`
- `src/vibe_carlo/static/js/charts.js` (factored chart helpers, used by both pages)
- `tests/test_public_index.py`
- `tests/test_client_sim_parity.py`

**Modified:**
- `src/vibe_carlo/app.py` (cache JSON at startup; bifurcate `index()`)
- `src/vibe_carlo/templates/base.html` (add `{% else %}` Login link in two nav blocks)
- `src/vibe_carlo/templates/index.html` (replace inline chart-rendering JS with a call into the new `charts.js`)
- `README.md` (document Node ≥ 18 as optional dev dep for full test coverage)

**Not modified** (deliberately): `simulation/engine.py`, `simulation/tax.py`, `simulation/distributions.py`, `schemas.py`, `db.py`, `auth.py`, `snapshots.py`, `plans.py`, `statements.py`, `timeline.py`, all other templates and tests, `pyproject.toml`. No new Python dependencies. No new server routes. No DB changes.

## Risks & mitigations

- **PRNG differences between Python (PCG64) and JS (mulberry32) prevent direct seed-based parity.** Mitigation: end-to-end parity tests inject pre-computed indices and spending samples instead of relying on seed reproducibility. Pure-function parity (tax math) doesn't need RNG and is exact.
- **10,000 runs in JS could be slow on phones.** Mitigation: Float64Array typed arrays plus 500-run batches keep one batch in single-digit milliseconds on modern hardware. If a real user hits a slow device, the Stop button gives them an out, and we can ship a Web Worker version later as a localized change.
- **Inlining the historical CSV grows the HTML by ~3 KB.** Mitigation: trivial; gzip drops it further.
- **`base.html` edit has blast radius** — every authed page renders through it. Mitigation: tests #3 and #10 (regression: authed `/` is unchanged; public page lacks authed nav).
- **Node test dependency.** Mitigation: parity tests skip cleanly when Node isn't present, so the existing Python-only contributor workflow is unaffected.
