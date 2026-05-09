# Client-side Monte Carlo Simulation Page

## Summary

Provide a public, unauthenticated landing page at `/` that lets any visitor run the same Monte Carlo simulation that authenticated users get today, but with the entire computation running in the browser. No XHR / fetch traffic to the server during or after a simulation run. The historical returns dataset is inlined into the rendered HTML.

This is a **landing-page** experience — it exists so that a curious, unauthenticated visitor can try the tool. Authenticated users continue to see the existing server-rendered `/` exactly as it works today (snapshots, plans, timeline, statements, etc.).

## In scope

1. A new public page served at `/` for visitors **without** a valid session cookie.
   - Currently `GET /` redirects unauthenticated visitors to `/login`. That redirect goes away; instead we render the new client-side page.
   - Authenticated users still get the existing server-backed `/` (unchanged).
2. The new page mirrors the **simulation** portion of the current `/` UI:
   - Portfolio inputs: Cash, Market/Stocks, Bonds (dollars).
   - Annual cash flows: Earnings, Spending distribution.
   - Spending distribution picker supporting all three types: flat, uniform, truncated normal — same UI as today (re-uses the existing `distribution_picker.html` macro and `distribution_picker.js`).
   - Tax settings: Filing status dropdown (None / Single / MFJ / MFS / HoH) — same options as today.
   - Years to simulate (1–80).
3. Simulation runs entirely in JavaScript:
   - 10,000 paths, fixed.
   - Same algorithm as `simulation/engine.py`: block bootstrap resampling, blended nominal return, real-return deflation, year-by-year compounding, $0 floor, success-rate computation.
   - Same tax gross-up logic as `simulation/tax.py` for traditional-account withdrawals when filing status is set.
   - Same outputs: fan chart (10/25/50/75/90 percentiles), success rate, final-year histogram, plus the federal-tax-adjustment summary box when filing status is set.
4. Progressive run UX:
   - Progress text updates live as runs accumulate, e.g. `4,300 of 10,000 runs completed`.
   - A **Stop** button is shown while the run is in progress. Clicking it halts further runs and renders the charts + success rate using only the runs completed so far.
   - When stopped early, the results panel makes it visually clear that the numbers reflect a partial run (e.g. `Stopped at 4,300 / 10,000 runs`).
5. Historical data delivery: the CSV (`src/vibe_carlo/data/historical_returns.csv`) is parsed at server startup (it already is) and rendered into the public page as an inlined JSON `<script>` tag. No separate HTTP request is needed to load it.

## Out of scope (explicitly removed from this page)

- **Snapshots** — no Save Snapshot button, no snapshot modal, no snapshot loading via `?snapshot_id=`. Snapshots are an authenticated-user feature only.
- **Plans, Timeline, Statements** — not surfaced on the public page. The header nav for those still appears for authenticated users only.
- **Advanced "sample block length" setting** — not exposed in the public page UI. The simulation always uses `block_length = years_to_simulate` (the current default when the field is left blank).
- **Server-side `/simulate` endpoint** — keep it as-is. It still backs the authenticated `/` page, so removing it would be a regression. The new public page simply does not call it.

## User-visible behaviour

- An unauthenticated visitor lands on `/`.
- They see a simulation form with sensible defaults (the same defaults the existing logged-in page uses for new users: `cash=300_000, market=2_000_000, bond=0, earnings=400_000, spending=truncated_normal(low=55k, high=100k, mean=74k, stddev=5k), years=30, filing_status=single`).
- They click **Run Simulation**. The button is replaced by **Stop**, and a progress line shows `X of 10,000 runs completed`. Progress updates at least a few times per second (UI does not freeze).
- When the run completes, the **Stop** button reverts to **Run Simulation** and the fan chart, success rate, tax-adjustment box (if applicable), and histogram render — exactly as on the authenticated page.
- If the user clicks **Stop** mid-run, the run halts immediately and the charts render using the runs completed so far. A small label notes that the result is partial.
- If the user re-runs, the previous charts are cleared and a fresh run begins.
- A clearly visible **Login** link is present on the page (in the header, where the authenticated nav normally lives) so the visitor can sign in if they want the full feature set. The existing login flow at `/login` is unchanged.

## Acceptance criteria

1. With no session cookie, `GET /` returns 200 with the new client-side page (not a redirect).
2. With a valid session cookie, `GET /` returns the existing authenticated index unchanged.
3. The page makes **zero** HTTP requests after the initial page load except for static assets (`/static/...`) and CDN scripts that the existing `base.html` already loads (Tailwind, htmx, Plotly, distribution_picker.js). No `fetch` / `XHR` / `htmx` calls to any vibe_carlo API endpoint. Following the visible Login link to `/login` is, of course, allowed.
4. Given identical inputs and a fixed RNG seed, the JS simulation produces results that match the Python `run_simulation` output to a small numerical tolerance. (See TEST.md for the parity test.)
5. The Stop button interrupts within ~one batch (≤ 500 runs of additional work) and renders partial results.
6. Existing tests for `/simulate`, snapshots, plans, timeline, and statements continue to pass.

## Open questions / follow-ups (not blocking this feature)

- Whether to add a "Sign up to save snapshots" call-to-action on the public page. Out of scope for now.
- Future SEO / share-link work (deep-linkable simulation parameters via URL hash). Out of scope.
