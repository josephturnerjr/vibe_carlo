# Architecture — Client-side Monte Carlo Simulation Page

## Overview

The feature is implemented as a **bifurcated `GET /` route** plus a small amount of **new client-side code**. No new server endpoints, no new database tables, no new dependencies, no new environment variables. The historical returns dataset is already loaded at server startup by the existing `lifespan()` hook; we simply serialize it once into the rendered HTML for unauthenticated visitors.

The split is the smallest one that satisfies the spec:
- **Server**: render a new template when the visitor has no session; render the existing template otherwise.
- **Browser**: a new JS module that ports `simulation/engine.py` + `simulation/tax.py` + `simulation/distributions.py` into the browser, plus a thin glue layer that drives the form / progress / Stop / results.

## Diagram

```
                 ┌─────────────────────────────────────────────────────────────────────┐
                 │                       BROWSER (unauthenticated)                     │
                 │                                                                     │
                 │   public_index.html (NEW template)                                  │
                 │   ┌───────────────────────────────────────────────────────────┐    │
                 │   │ <script type="application/json" id="historical-data">     │    │
                 │   │    [[0.4381,0.0084,-0.0116], ...]   ← inlined CSV         │    │
                 │   │ </script>                                                  │    │
                 │   │                                                            │    │
                 │   │ Header: vibe_carlo  ……………………………………  [ Login ]            │    │
                 │   │                                                            │    │
                 │   │ <form id="sim-form">  (re-uses distribution_picker macro) │    │
                 │   │   cash / market / bond / earnings / spending / filing /   │    │
                 │   │   years_to_simulate                                       │    │
                 │   │   [ Run Simulation ] / [ Stop ]   "4,300 of 10,000 done" │    │
                 │   │ </form>                                                    │    │
                 │   │                                                            │    │
                 │   │ <div id="results"> … fan chart, success %, histogram … </>│    │
                 │   └───────────────────────────────────────────────────────────┘    │
                 │            │ submit                                                 │
                 │            ▼                                                        │
                 │   ┌──────────────────────────────────┐ ┌─────────────────────────┐ │
                 │   │ NEW: static/js/client_sim.js      │ │ distribution_picker.js  │ │
                 │   │ ─────────────────────────────────  │ │      (existing)         │ │
                 │   │   runSimulation(params, data,      │ └─────────────────────────┘ │
                 │   │                 onProgress,        │ ┌─────────────────────────┐ │
                 │   │                 abortSignal)       │ │   Plotly  (CDN)         │ │
                 │   │   _buildBootstrapIndices()         │ │   Tailwind CSS (CDN)    │ │
                 │   │   _sampleSpending() ×3 dist types  │ │   htmx (CDN, unused on  │ │
                 │   │   _grossUpWithdrawalArray()        │ │     this page)          │ │
                 │   │   _computePercentiles()            │ └─────────────────────────┘ │
                 │   │   _renderResults() (DOM + Plotly)  │                             │
                 │   │   batch loop (500 runs / tick)     │                             │
                 │   └──────────────────────────────────┘                               │
                 └─────────────────────────────────────────────────────────────────────┘
                                            ▲
                                            │  ← initial page load only; no XHR after
                                            │
                 ┌─────────────────────────────────────────────────────────────────────┐
                 │                          FASTAPI SERVER                             │
                 │                                                                     │
                 │   lifespan() startup (EXISTING):                                    │
                 │     historical_data : np.ndarray (N, 3) = load_historical_data()   │
                 │     _historical_data_json : str = json.dumps(historical_data       │
                 │                                              .tolist())             │
                 │                                                                     │
                 │   GET /                                                             │
                 │     ├── _get_current_user(req) is None  ──►  TemplateResponse(     │
                 │     │                                          "public_index.html", │
                 │     │                                          {historical_data_json│
                 │     │                                           }) ◄── NEW BRANCH   │
                 │     │                                                               │
                 │     └── otherwise                       ──►  existing index.html    │
                 │                                              (UNCHANGED)            │
                 │                                                                     │
                 │   All other routes UNCHANGED:                                       │
                 │     POST /simulate, /snapshots*, /plans*, /timeline, /statements*,  │
                 │     /login, /logout                                                 │
                 └─────────────────────────────────────────────────────────────────────┘
```

## What's new (highlighted)

| Item | Path | Purpose |
|---|---|---|
| **NEW template** | `src/vibe_carlo/templates/public_index.html` | Unauthenticated landing page. Contains the form, the inlined `<script type="application/json">` historical data, the Login link, and the `#results` container. |
| **NEW JS module** | `src/vibe_carlo/static/js/client_sim.js` | Pure-JS port of the simulation engine + tax gross-up + distribution sampling, plus the form-submit / progress / Stop / Plotly-render glue. |
| **Module-level helper** | inside `app.py` | One-time JSON serialization of `historical_data` cached at startup so we don't re-serialize per request. |
| **Branch in `GET /`** | inside `app.py::index()` | Render `public_index.html` when there is no session; otherwise current behaviour. |

That is the entire delta. No new files outside those two; no new dependencies in `pyproject.toml`; no JS bundler / build step.

## What's reused

| Item | Why it just works |
|---|---|
| `templates/partials/distribution_picker.html` macro | Imported into `public_index.html`; renders the same flat / uniform / truncated_normal field group that the authenticated page uses. |
| `static/js/distribution_picker.js` | Already loaded by `base.html`. Drives the picker preview chart on the public page exactly the same way. |
| `static/css/custom.css`, Tailwind, Plotly | All loaded via the existing `base.html` `<head>`. |
| `templates/base.html` | Re-used as the public page's layout. The header already has a `{% if user_email %}` gate around the authenticated nav, so an unauthenticated render naturally hides the snapshots/plans/etc. links. We add an `{% else %}` arm with a `Login` link. |
| `simulation/engine.py`, `simulation/tax.py`, `simulation/distributions.py` | Stay exactly as-is and continue to back the authenticated `POST /simulate`. They are also the **reference implementation** the new JS module is ported from and tested against. |
| Existing default values | We use the same `cash=300_000, market=2_000_000, bond=0, earnings=400_000, spending=truncnorm(55k,100k,74k,5k), years=30, filing=single` defaults as the current `index.html`, by reusing the same template snippet pattern. |

## Data flow per simulation

1. Browser parses the `#historical-data` `<script>` once on page load → `Float64Array` columns (sp500, bond, cpi).
2. User clicks **Run Simulation**. `client_sim.js`:
   1. Reads form values, builds a `params` object that mirrors `SimulationInput`.
   2. Validates client-side (non-negative dollars, total > 0, low ≤ high, etc.).
   3. Initializes accumulator state: portfolios `Float64Array(years+1)` aggregating sums for percentiles, plus rolling `everHitZero` count, plus `finalDist` array.
   4. Loops in batches of 500 runs. After each batch:
      - Updates progress text (`X of 10,000 runs completed`).
      - Yields to the event loop with `await new Promise(r => setTimeout(r, 0))` so the UI stays responsive and a Stop click is processed.
      - Checks the abort flag; if set, breaks out of the loop.
   5. After loop ends (completed or stopped), computes percentiles from the accumulated portfolio paths and renders the results (fan chart + success rate + histogram + tax-adjustment box) using Plotly directly, with the same DOM structure as `partials/results.html`.

3. **No HTTP requests are made during steps 1–3 other than the initial page load.**

## Why this design

- **Smallest change to the server.** A single `if`/`else` branch in `index()` plus a one-time JSON serialization. We don't fork `base.html`, don't create a new auth flow, don't add routes.
- **Reuses existing UI primitives.** The distribution picker, Plotly, Tailwind, and the page layout already exist. We avoid reinventing anything visual.
- **Faithful port over fancy abstraction.** `client_sim.js` is a straight transliteration of the three Python modules — same variable names, same algorithm steps, same array shapes — so reading them side-by-side stays trivial. No build tools, no TypeScript, no shared-source-of-truth machinery.
- **Progress + Stop fall out of batching.** Doing 10,000 runs in one synchronous JS call would freeze the tab and prevent Stop from working. Batch + `setTimeout(0)` yields gives us both progress reporting and interrupt-ability with no extra infrastructure (no Web Worker, no `MessageChannel`, no AbortController-via-fetch). If perf becomes a problem later, swapping the batch loop for a Web Worker is a localized change.
