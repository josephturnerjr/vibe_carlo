# Test Plan — Client-side Monte Carlo Simulation Page

## Strategy

Two layers of automated tests, plus a short manual smoke checklist for things only a real browser can exercise.

1. **Python tests (`tests/test_public_index.py`)** — cover the server bifurcation, inlined-data correctness, and presence/absence of UI elements. Run as part of the existing `uv run pytest`.
2. **JS-parity tests (`tests/test_client_sim_parity.py`)** — invoke the new JS module via `subprocess.run(["node", ...])` with deterministic inputs, then compare the JS output to the Python reference implementation. Tests `pytest.skip()` if `node` is not on `PATH`, so contributors without Node installed don't see red. README documents Node ≥ 18 as an optional dev dep for full coverage.
3. **Manual smoke checklist** — for Stop-button behavior, live progress text, and chart rendering. Documented at the bottom of this file.

Rationale for not adding a full JS test runner / Playwright: the JS module's pure functions can be tested headlessly via Node, and the parity test is the strongest possible correctness signal because it compares directly against the Python reference. Adding a JS framework, browser harness, or build step would be more infrastructure than the feature warrants.

To make the parity tests possible, `client_sim.js` is structured so that the **pure simulation logic** (sampling, bootstrap, gross-up, compounding, percentiles) is exported from a small ES module that Node can `import` with no DOM dependencies. The DOM/UI glue (form parsing, Plotly rendering, batch loop, Stop button, progress text) lives in a thin separate file that imports from the pure module and is exercised by the manual smoke checklist instead.

## Layer 1 — Python tests (`tests/test_public_index.py`)

**Server bifurcation — happy path:**
1. `test_get_root_unauthenticated_returns_200` — no session cookie → 200, body contains a marker unique to `public_index.html` (e.g. the inlined `<script id="historical-data">`).
2. `test_get_root_unauthenticated_does_not_redirect` — explicitly asserts response is not a 3xx to `/login`.
3. `test_get_root_authenticated_unchanged` — with a valid session cookie, body contains the existing markers (e.g. snapshot modal, `hx-post="/simulate"`) and does **not** contain the public-page markers. Regression check that we didn't accidentally change the authed page.

**Inlined historical data — correctness:**
4. `test_inlined_historical_data_matches_csv` — parse the JSON out of the `<script id="historical-data">` block and assert it equals `load_historical_data().tolist()` element-for-element.
5. `test_inlined_historical_data_shape` — JSON is a list of length N where N matches the CSV row count, each row has exactly 3 floats. Edge: confirms we don't accidentally truncate or transpose.
6. `test_inlined_historical_data_year_count_matches` — sanity: row count equals `2024 - 1928 + 1 = 97`.

**UI element presence/absence:**
7. `test_public_page_has_login_link` — body contains `href="/login"` in the header area, and the link text contains "Login" (case-insensitive).
8. `test_public_page_has_no_snapshot_ui` — body contains none of: `id="snapshot-modal"`, `id="save-snapshot-btn"`, `hx-post="/snapshots/save"`.
9. `test_public_page_has_no_advanced_sample_years` — body contains no `name="sample_years"` input.
10. `test_public_page_has_no_authenticated_nav` — body contains no link to `/snapshots`, `/plans`, `/timeline`, `/statements` (those are authenticated-only).
11. `test_public_page_distribution_picker_present` — body contains the three distribution-type options (`flat`, `uniform`, `truncated_normal`) so we know the macro is wired in.
12. `test_public_page_filing_status_options_present` — body contains all five filing-status `<option>` values.

**Edge case — repeated requests don't re-serialize:**
13. `test_inlined_data_is_cached_at_startup` — instrument or measure: the JSON-stringified historical data is computed once during `lifespan()` and reused. Implementation-checking, not behavior-checking; can be a simple `id()` comparison via a probe function.

## Layer 2 — JS-parity tests (`tests/test_client_sim_parity.py`)

Each test builds a small Node script as a string, pipes deterministic inputs as JSON via stdin or argv, executes the JS function, parses the JSON the script prints, and asserts agreement with the Python reference.

**Tax gross-up — exact parity (deterministic, no RNG):**
14. `test_js_gross_up_scalar_each_filing_status` — for each of the four `FilingStatus` values, assert JS `_grossUpWithdrawal(spending)` matches Python `gross_up_withdrawal(spending, fs)` to ≤ 1e-9 absolute. Spending values: `[0, 1, 100, 16_099, 16_100, 16_101, 50_000, 100_000, 250_000, 750_000, 5_000_000]` — chosen to land on bracket boundaries and the standard-deduction edge for each filing status.
15. `test_js_gross_up_array_form` — JS array form on `[0, 50_000, 100_000, 250_000, 750_000]` matches Python `gross_up_withdrawal_array` element-wise.
16. `test_js_gross_up_zero_and_negative_clamped` — `[0, -100, -1e9]` → `[0, 0, 0]` (Python clamps; JS must too).
17. `test_js_gross_up_into_top_bracket` — extremely large spending (e.g. `$10M`) confirms the top 37% bracket is reached and the math is identical.

**Block-bootstrap indices — structural:**
18. `test_js_bootstrap_indices_shape` — calling JS `_buildBootstrapIndices(seed=..., nRuns=100, years=30, blockLen=30, nHistorical=97)` returns an array of length 100, each row length 30.
19. `test_js_bootstrap_indices_in_range` — every index is in `[0, 96]`.
20. `test_js_bootstrap_indices_contiguous_within_block` — each block of length `blockLen` starts at some `s` and contains exactly `[s, s+1, ..., s+blockLen-1]`.
21. `test_js_bootstrap_indices_handles_partial_trailing_block` — `years=70, blockLen=30, nHistorical=97`: rows are 30+30+10, last segment is contiguous of length 10 starting at some valid `s`.
22. `test_js_bootstrap_indices_max_start_respected` — for the smallest possible historical window (`blockLen == nHistorical`), every block must start at index 0 (only valid start). Edge: covers the off-by-one in `max_start = n_historical - block_len`.
23. `test_js_bootstrap_indices_block_len_one` — `blockLen=1`: indices are independent uniform draws over `[0, nHistorical-1]`. Edge: smallest block.

**Distribution sampling — statistical correctness:**
24. `test_js_sample_flat` — flat dist: 1,000 samples are all exactly equal to `value`.
25. `test_js_sample_uniform_in_range` — uniform 1,000 samples all in `[low, high]`.
26. `test_js_sample_uniform_mean_converges` — 50,000 samples from `Uniform(0, 100)`: sample mean within 1.0 of 50.
27. `test_js_sample_truncated_normal_in_range` — every sample within `[low, high]` (rejection sampling correctness).
28. `test_js_sample_truncated_normal_mean_converges` — 50,000 samples from `TN(low=40, high=60, mean=50, stddev=5)`: sample mean within 0.2 of 50 (symmetric).
29. `test_js_sample_truncated_normal_skewed` — 50,000 samples from `TN(low=0, high=100, mean=80, stddev=20)`: sample mean is shifted left of 80 (truncation skew). Compare JS sample mean to Python sample mean (large N) within 0.5.
30. `test_js_sample_truncated_normal_narrow_truncation` — `TN(low=49.99, high=50.01, mean=50, stddev=10)` — extreme rejection rate. Confirm JS doesn't infinite-loop and produces values in range. (Use a hard timeout.)

**End-to-end engine parity (with injected indices + spending samples):**

These tests call a JS entry point that accepts pre-computed bootstrap indices and pre-computed spending samples (i.e., the RNG-dependent inputs are injected, eliminating PRNG-implementation differences). The Python reference does the same work via the same injected arrays.

31. `test_js_engine_e2e_no_tax_flat_spending` — params: `cash=100k, market=400k, bond=0, earnings=50k, spending=flat(60k), years=30`, indices = `[[0..29]] * 100`, spending = `[[60_000]*30] * 100`. Assert JS percentiles, success_rate, final_year_distribution match Python within 1e-6 relative.
32. `test_js_engine_e2e_with_tax_truncated_normal_spending` — params: `filing=single, spending=truncnorm(...)`, randomly-but-fixed injected samples. Assert match within 1e-6 relative.
33. `test_js_engine_e2e_zero_earnings_high_spending` — portfolio runs to zero quickly; success_rate near 0; floor at $0 enforced. Edge case: portfolio array clamps non-negative.
34. `test_js_engine_e2e_huge_earnings_no_withdrawal` — earnings ≫ spending; success_rate = 1.0; gross_withdrawal = 0; portfolio grows monotonically. Edge.
35. `test_js_engine_e2e_one_year_one_run` — degenerate inputs: `years=1, n_runs=1, blockLen=1`. Confirms shape correctness on the smallest case. Edge.
36. `test_js_engine_e2e_block_len_equals_years` — single-block bootstrap (current default behavior on the public page) — confirms indices reduce to a single contiguous block per run.
37. `test_js_engine_percentiles_include_year_zero` — `year_labels[0] == 0` and `percentiles[*][0] == total_portfolio` for all percentiles. Catches off-by-one in time-axis indexing. Edge.
38. `test_js_engine_success_rate_range` — `0.0 ≤ success_rate ≤ 1.0` for any inputs. Sanity.

**Partial-run output (stop-mid-flight):**

These test the exposed JS function that computes results from the first `k < n_runs` runs (the same code path the Stop button uses).

39. `test_js_partial_results_match_full_when_k_equals_n` — calling the partial-results computation with `k = n_runs` produces identical output to the full run. Sanity: partial and full paths agree.
40. `test_js_partial_results_smaller_k_produces_valid_output` — `k = 100`: output has correct shapes, percentiles within input range, success_rate in `[0, 1]`. Catches divide-by-zero or empty-array bugs.
41. `test_js_partial_results_k_zero_handled` — `k = 0` (Stop pressed before any batch finished): function returns a sentinel (e.g. `null`) that the UI knows to display as "no results yet" rather than crashing.

## Layer 3 — Manual smoke checklist

To be run by the developer in a real browser before merging. Documented in the PR description.

- [ ] Open `/` in an incognito tab. Page loads with the form and Login link visible. Snapshot/Plans/Timeline/Statements links are NOT visible.
- [ ] Open browser dev tools → Network tab → filter to XHR/fetch. Click **Run Simulation**. Verify NO requests to `/simulate`, `/snapshots`, or any other API endpoint fire during or after the run.
- [ ] During the run, the progress text updates visibly (not stuck on "0 of 10,000"). Final value reads "10,000 of 10,000 runs completed" (or whatever the spec wording is).
- [ ] The Run button changes to a Stop button while running, and reverts when the run completes.
- [ ] Click **Stop** at roughly the halfway point. The run halts within ~1 second. The fan chart, success rate, and histogram render based on the partial data, and a label on the page makes it clear the result is partial (e.g. "Stopped at 4,300 / 10,000 runs").
- [ ] Switch the spending distribution between Flat / Uniform / Truncated Normal. The picker preview chart updates as on the authenticated page.
- [ ] Run with each filing-status option (None, Single, MFJ, MFS, HoH). The federal-tax-adjustment summary box appears for all four non-None options and matches the layout of the authenticated page.
- [ ] On a logged-in tab (separate browser profile), `/` still shows the existing authenticated UI with snapshot save modal and full nav.
- [ ] Click Login link → lands on `/login` page. Existing login flow works.
- [ ] Mobile viewport (DevTools responsive mode, e.g. iPhone 13): form is usable, charts render.

## Coverage rationale (edge cases addressed)

- **Off-by-one in bootstrap window**: tests #20, #22 cover `max_start = n - block_len` and the case where only one start index is valid.
- **Off-by-one in time axis**: test #37 confirms year 0 is included with the initial portfolio value.
- **Partial trailing block in bootstrap**: test #21 covers `years > block_len` where the final block is shorter than `block_len`.
- **$0 floor**: test #33.
- **Earnings ≥ spending (no withdrawal needed)**: test #34.
- **Top-bracket tax math**: test #17.
- **Standard-deduction boundary**: test #14 spending values straddle each filing status's std-deduction.
- **Truncated-normal with extreme rejection rate**: test #30 catches infinite-loop bugs.
- **Stop-before-any-results**: test #41 catches divide-by-zero / NaN output when `k=0`.
- **Public-page contamination of authed page**: test #3 regression guard.
- **Inlined data correctness**: tests #4–#6 catch silent CSV-parsing breakage.
- **Auth boundary**: tests #1, #2, #3 confirm both branches of the new `if`/`else`.
