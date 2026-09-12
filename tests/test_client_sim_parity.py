"""Parity tests: invoke the JS client_sim module via Node and compare to Python.

Node is located in this order:

1. ``$VIBE_CARLO_NODE`` — a path to anything that behaves like the ``node``
   binary. ``scripts/run-js-tests.sh`` sets this to ``scripts/node-docker``,
   which runs Node in a container, so these tests are runnable on a machine
   with no local Node install.
2. ``node`` on ``PATH``.

If neither is available the tests skip, so the suite stays green for
contributors who have set up neither Node nor Docker.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from vibe_carlo.schemas import (
    FlatDistribution,
    SimulationInput,
    TruncatedNormalDistribution,
)
from vibe_carlo.simulation.engine import _build_bootstrap_indices, run_simulation
from vibe_carlo.simulation.models import load_historical_data
from vibe_carlo.simulation.solver import SUCCESS_LEVELS

CLIENT_SIM_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "vibe_carlo"
    / "static"
    / "js"
    / "client_sim.js"
)


@pytest.fixture(scope="module")
def node_bin() -> str:
    override = os.environ.get("VIBE_CARLO_NODE")
    if override:
        return override
    path = shutil.which("node")
    if path is None:
        pytest.skip(
            "No Node.js: install Node >= 18, or run scripts/run-js-tests.sh "
            "to run these against a Node container"
        )
    assert path is not None
    return path


def _run_js(node_bin: str, body: str, data: dict[str, Any] | None = None) -> Any:
    """Run a snippet with ClientSim already imported; return the JSON it prints.

    Bulk arrays go in `data`, which arrives on stdin as the global `DATA`.
    Inlining them in the script instead would blow Linux's 128KB limit on a
    single argv entry.
    """
    preamble = (
        f"const ClientSim = require({json.dumps(str(CLIENT_SIM_PATH))});\n"
        "function emit(v) {\n"
        "  process.stdout.write(JSON.stringify(v, function(_, x) {\n"
        "    if (\n"
        "      x instanceof Float64Array\n"
        "      || x instanceof Int32Array\n"
        "      || x instanceof Uint8Array\n"
        "    ) { return Array.from(x); }\n"
        "    return x;\n"
        "  }));\n"
        "}\n"
    )
    if data is not None:
        preamble += "const DATA = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"

    proc = subprocess.run(
        [node_bin, "-e", preamble + body],
        input=json.dumps(data) if data is not None else "",
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"node failed: {proc.stderr}")
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# Block-bootstrap indices — structural
# ---------------------------------------------------------------------------


def _js_bootstrap(
    node_bin: str, seed: int, n_runs: int, years: int, block_len: int, n_hist: int
) -> list[list[int]]:
    flat = _run_js(
        node_bin,
        f"const rng = ClientSim.makeRng({seed});\n"
        "const idx = ClientSim.buildBootstrapIndices(\n"
        f"  rng, {n_runs}, {years}, {block_len}, {n_hist}\n"
        ");\n"
        "emit(Array.from(idx));",
    )
    return [flat[r * years : (r + 1) * years] for r in range(n_runs)]


def test_js_bootstrap_indices_shape(node_bin: str) -> None:
    rows = _js_bootstrap(node_bin, seed=42, n_runs=100, years=30, block_len=30, n_hist=97)
    assert len(rows) == 100
    assert all(len(r) == 30 for r in rows)


def test_js_bootstrap_indices_in_range(node_bin: str) -> None:
    rows = _js_bootstrap(node_bin, seed=1, n_runs=50, years=20, block_len=20, n_hist=97)
    for row in rows:
        for v in row:
            assert 0 <= v <= 96


def test_js_bootstrap_indices_contiguous_within_block(node_bin: str) -> None:
    block_len = 5
    years = 10
    rows = _js_bootstrap(node_bin, seed=7, n_runs=20, years=years, block_len=block_len, n_hist=97)
    for row in rows:
        for start in range(0, years, block_len):
            block = row[start : start + block_len]
            for i in range(1, len(block)):
                assert block[i] == block[0] + i


def test_js_bootstrap_indices_handles_partial_trailing_block(node_bin: str) -> None:
    block_len = 30
    years = 70
    rows = _js_bootstrap(node_bin, seed=3, n_runs=10, years=years, block_len=block_len, n_hist=97)
    for row in rows:
        # rows are 30+30+10
        for chunk_start in (0, 30, 60):
            chunk_len = min(block_len, years - chunk_start)
            chunk = row[chunk_start : chunk_start + chunk_len]
            for i in range(1, len(chunk)):
                assert chunk[i] == chunk[0] + i


def test_js_bootstrap_indices_max_start_respected(node_bin: str) -> None:
    # block_len == n_historical: only valid start is 0
    rows = _js_bootstrap(node_bin, seed=99, n_runs=20, years=97, block_len=97, n_hist=97)
    for row in rows:
        assert row[0] == 0
        for i, v in enumerate(row):
            assert v == i


def test_js_bootstrap_indices_block_len_one(node_bin: str) -> None:
    rows = _js_bootstrap(node_bin, seed=5, n_runs=200, years=50, block_len=1, n_hist=97)
    for row in rows:
        for v in row:
            assert 0 <= v <= 96
    # Sanity: variance is high (independent draws each year)
    flat = [v for row in rows for v in row]
    assert len(set(flat)) > 50


# ---------------------------------------------------------------------------
# Distribution sampling — statistical
# ---------------------------------------------------------------------------


def test_js_sample_flat(node_bin: str) -> None:
    out = _run_js(
        node_bin,
        "const rng = ClientSim.makeRng(1);\n"
        "emit(Array.from(ClientSim.sampleFlat(42.5, 100, 10)));",
    )
    assert len(out) == 1000
    assert all(v == 42.5 for v in out)


def test_js_sample_uniform_in_range(node_bin: str) -> None:
    out = _run_js(
        node_bin,
        "const rng = ClientSim.makeRng(1);\n"
        "emit(Array.from(ClientSim.sampleUniform(10, 20, 100, 10, rng)));",
    )
    assert all(10 <= v <= 20 for v in out)


def test_js_sample_uniform_mean_converges(node_bin: str) -> None:
    out = _run_js(
        node_bin,
        "const rng = ClientSim.makeRng(123);\n"
        "emit(Array.from(ClientSim.sampleUniform(0, 100, 50000, 1, rng)));",
    )
    mean = sum(out) / len(out)
    assert abs(mean - 50.0) < 1.0


def test_js_sample_truncated_normal_in_range(node_bin: str) -> None:
    out = _run_js(
        node_bin,
        "const rng = ClientSim.makeRng(7);\n"
        "emit(Array.from(ClientSim.sampleTruncatedNormal(40, 60, 50, 5, 1000, 5, rng)));",
    )
    assert all(40 <= v <= 60 for v in out)


def test_js_sample_truncated_normal_mean_converges(node_bin: str) -> None:
    out = _run_js(
        node_bin,
        "const rng = ClientSim.makeRng(11);\n"
        "emit(Array.from(ClientSim.sampleTruncatedNormal(40, 60, 50, 5, 50000, 1, rng)));",
    )
    mean = sum(out) / len(out)
    assert abs(mean - 50.0) < 0.2


def test_js_sample_truncated_normal_skewed(node_bin: str) -> None:
    out = _run_js(
        node_bin,
        "const rng = ClientSim.makeRng(13);\n"
        "emit(Array.from(ClientSim.sampleTruncatedNormal(0, 100, 80, 20, 50000, 1, rng)));",
    )
    js_mean = sum(out) / len(out)
    # Compare to a Python large-N reference using the same TN distribution
    rng = np.random.default_rng(0)
    samples = []
    while len(samples) < 50_000:
        cand = rng.normal(80, 20, size=20_000)
        samples.extend(cand[(cand >= 0) & (cand <= 100)].tolist())
    py_mean = float(np.mean(samples[:50_000]))
    assert abs(js_mean - py_mean) < 0.5


def test_js_sample_truncated_normal_narrow_truncation(node_bin: str) -> None:
    # Extreme rejection rate; must not infinite-loop and must produce in-range values.
    out = _run_js(
        node_bin,
        "const rng = ClientSim.makeRng(2);\n"
        "emit(Array.from(ClientSim.sampleTruncatedNormal(49.99, 50.01, 50, 10, 100, 1, rng)));",
    )
    assert len(out) == 100
    assert all(49.99 <= v <= 50.01 for v in out)


# ---------------------------------------------------------------------------
# End-to-end engine parity (with injected indices + spending samples)
# ---------------------------------------------------------------------------


def _engine_e2e_compare(
    node_bin: str,
    params: SimulationInput,
    indices: np.ndarray,
    spending: np.ndarray,
    historical: np.ndarray,
) -> None:
    """Run JS runEngineCore + computeResults, compare to Python on injected arrays."""
    n_runs, years = indices.shape
    indices_flat = indices.flatten().tolist()
    spending_flat = spending.flatten().tolist()
    hist_flat = historical.flatten().tolist()

    js_params = {
        "cash_value": params.cash_value,
        "market_value": params.market_value,
        "bond_value": params.bond_value,
        "earnings": params.earnings,
        "years_to_simulate": params.years_to_simulate,
        "withdrawal_tax_rate": params.withdrawal_tax_rate,
    }
    js_out = _run_js(
        node_bin,
        f"const params = {json.dumps(js_params)};\n"
        f"const idx = new Int32Array({json.dumps(indices_flat)});\n"
        f"const spend = new Float64Array({json.dumps(spending_flat)});\n"
        f"const hist = new Float64Array({json.dumps(hist_flat)});\n"
        "const out = ClientSim.runEngineCore(params, idx, spend, hist);\n"
        f"emit(ClientSim.computeResults(out, {n_runs}, params));",
    )

    py_out = _run_python_engine(params, indices, spending, historical)

    # Compare percentiles, success_rate, final_year_distribution
    for key in ("p10", "p25", "p50", "p75", "p90"):
        for js_v, py_v in zip(js_out["percentiles"][key], py_out["percentiles"][key]):
            assert abs(js_v - py_v) < 1e-6, f"{key} mismatch: {js_v} vs {py_v}"
    assert abs(js_out["success_rate"] - py_out["success_rate"]) < 1e-9
    for js_v, py_v in zip(js_out["final_year_distribution"], py_out["final_year_distribution"]):
        assert abs(js_v - py_v) < 1e-6
    if params.withdrawal_tax_rate > 0:
        assert abs(js_out["gross_withdrawal"] - py_out["gross_withdrawal"]) < 1e-3
        assert abs(js_out["effective_tax_rate"] - py_out["effective_tax_rate"]) < 1e-9
    else:
        assert js_out["gross_withdrawal"] is None
        assert js_out["effective_tax_rate"] is None


def _run_python_engine(
    params: SimulationInput,
    indices: np.ndarray,
    spending: np.ndarray,
    historical: np.ndarray,
) -> dict[str, Any]:
    """Replicate engine.run_simulation but with injected arrays (no RNG)."""
    from vibe_carlo.simulation.models import COL_BOND, COL_CPI, COL_SP500

    years = params.years_to_simulate
    n_runs = indices.shape[0]

    shortfall = np.maximum(spending - params.earnings, 0.0)
    surplus = np.maximum(params.earnings - spending, 0.0)

    if params.withdrawal_tax_rate > 0:
        gross_withdrawals = shortfall / (1.0 - params.withdrawal_tax_rate)
    else:
        gross_withdrawals = shortfall

    total_portfolio = params.cash_value + params.market_value + params.bond_value
    market_alloc = params.market_value / total_portfolio
    bond_alloc = params.bond_value / total_portfolio

    sampled_data = historical[indices]
    sp500 = sampled_data[:, :, COL_SP500]
    bond = sampled_data[:, :, COL_BOND]
    cpi = sampled_data[:, :, COL_CPI]
    nominal = market_alloc * sp500 + bond_alloc * bond
    real_return = (1 + nominal) / (1 + cpi) - 1

    portfolios = np.zeros((n_runs, years + 1), dtype=np.float64)
    portfolios[:, 0] = total_portfolio
    ever_hit_zero = np.zeros(n_runs, dtype=bool)
    for y in range(years):
        v = portfolios[:, y]
        v = v * (1 + real_return[:, y])
        v = v + surplus[:, y] - gross_withdrawals[:, y]
        v = np.maximum(v, 0.0)
        portfolios[:, y + 1] = v
        ever_hit_zero |= v == 0.0

    success_rate = float(1.0 - np.mean(ever_hit_zero))
    percentiles = {
        f"p{p}": np.percentile(portfolios, p, axis=0).tolist() for p in (10, 25, 50, 75, 90)
    }
    final = portfolios[:, -1].tolist()

    gross = etr = None
    if params.withdrawal_tax_rate > 0:
        gross = float(np.mean(gross_withdrawals))
        etr = params.withdrawal_tax_rate

    return {
        "percentiles": percentiles,
        "success_rate": success_rate,
        "final_year_distribution": final,
        "gross_withdrawal": gross,
        "effective_tax_rate": etr,
    }


def test_js_engine_e2e_no_tax_flat_spending(node_bin: str) -> None:
    historical = load_historical_data()
    n_runs, years = 100, 30
    indices = np.tile(np.arange(years, dtype=np.int32), (n_runs, 1))
    spending = np.full((n_runs, years), 60_000.0)
    params = SimulationInput(
        cash_value=100_000,
        market_value=400_000,
        bond_value=0,
        earnings=50_000,
        spending_distribution=FlatDistribution(value=60_000),
        years_to_simulate=years,
    )
    _engine_e2e_compare(node_bin, params, indices, spending, historical)


def test_js_engine_e2e_with_tax_truncated_normal_spending(node_bin: str) -> None:
    historical = load_historical_data()
    n_runs, years = 50, 25
    rng = np.random.default_rng(123)
    indices = rng.integers(0, len(historical) - years + 1, size=(n_runs, 1)).astype(np.int32)
    indices = np.broadcast_to(indices, (n_runs, years)).copy()
    indices = indices + np.arange(years, dtype=np.int32)
    spending = rng.normal(74_000, 5_000, size=(n_runs, years)).clip(55_000, 100_000)
    params = SimulationInput(
        cash_value=300_000,
        market_value=2_000_000,
        bond_value=0,
        earnings=400_000,
        spending_distribution=TruncatedNormalDistribution(
            low=55_000, high=100_000, mean=74_000, stddev=5_000
        ),
        years_to_simulate=years,
        withdrawal_tax_rate=0.22,
    )
    _engine_e2e_compare(node_bin, params, indices, spending, historical)


def test_js_engine_e2e_zero_earnings_high_spending(node_bin: str) -> None:
    historical = load_historical_data()
    n_runs, years = 30, 20
    indices = np.tile(np.arange(years, dtype=np.int32), (n_runs, 1))
    spending = np.full((n_runs, years), 200_000.0)
    params = SimulationInput(
        cash_value=10_000,
        market_value=10_000,
        bond_value=0,
        earnings=0,
        spending_distribution=FlatDistribution(value=200_000),
        years_to_simulate=years,
    )
    _engine_e2e_compare(node_bin, params, indices, spending, historical)


def test_js_engine_e2e_huge_earnings_no_withdrawal(node_bin: str) -> None:
    historical = load_historical_data()
    n_runs, years = 20, 10
    indices = np.tile(np.arange(years, dtype=np.int32), (n_runs, 1))
    spending = np.full((n_runs, years), 1_000.0)
    params = SimulationInput(
        cash_value=100_000,
        market_value=100_000,
        bond_value=0,
        earnings=500_000,
        spending_distribution=FlatDistribution(value=1_000),
        years_to_simulate=years,
        withdrawal_tax_rate=0.15,
    )
    _engine_e2e_compare(node_bin, params, indices, spending, historical)


def test_js_engine_e2e_one_year_one_run(node_bin: str) -> None:
    historical = load_historical_data()
    indices = np.array([[0]], dtype=np.int32)
    spending = np.array([[5_000.0]])
    params = SimulationInput(
        cash_value=10_000,
        market_value=0,
        bond_value=0,
        earnings=0,
        spending_distribution=FlatDistribution(value=5_000),
        years_to_simulate=1,
    )
    _engine_e2e_compare(node_bin, params, indices, spending, historical)


def test_js_engine_e2e_block_len_equals_years(node_bin: str) -> None:
    historical = load_historical_data()
    n_runs, years = 25, 30
    rng = np.random.default_rng(0)
    starts = rng.integers(0, len(historical) - years + 1, size=n_runs).astype(np.int32)
    indices = (starts[:, None] + np.arange(years, dtype=np.int32)[None, :]).astype(np.int32)
    spending = np.full((n_runs, years), 30_000.0)
    params = SimulationInput(
        cash_value=50_000,
        market_value=200_000,
        bond_value=0,
        earnings=20_000,
        spending_distribution=FlatDistribution(value=30_000),
        years_to_simulate=years,
    )
    _engine_e2e_compare(node_bin, params, indices, spending, historical)


def test_js_engine_percentiles_include_year_zero(node_bin: str) -> None:
    historical = load_historical_data()
    n_runs, years = 10, 15
    indices = np.tile(np.arange(years, dtype=np.int32), (n_runs, 1))
    spending = np.full((n_runs, years), 10_000.0)
    params = SimulationInput(
        cash_value=100_000,
        market_value=0,
        bond_value=0,
        earnings=0,
        spending_distribution=FlatDistribution(value=10_000),
        years_to_simulate=years,
    )
    params_dict = {
        "cash_value": 100_000,
        "market_value": 0,
        "bond_value": 0,
        "earnings": 0,
        "years_to_simulate": years,
        "withdrawal_tax_rate": 0,
    }
    js_out = _run_js(
        node_bin,
        f"const params = {json.dumps(params_dict)};\n"
        f"const idx = new Int32Array({json.dumps(indices.flatten().tolist())});\n"
        f"const spend = new Float64Array({json.dumps(spending.flatten().tolist())});\n"
        f"const hist = new Float64Array({json.dumps(historical.flatten().tolist())});\n"
        "const out = ClientSim.runEngineCore(params, idx, spend, hist);\n"
        f"emit(ClientSim.computeResults(out, {n_runs}, params));",
    )
    assert js_out["year_labels"][0] == 0
    for p in ("p10", "p25", "p50", "p75", "p90"):
        assert abs(js_out["percentiles"][p][0] - params.cash_value) < 1e-9


def test_js_engine_success_rate_range(node_bin: str) -> None:
    """Sanity: success_rate must be in [0, 1] no matter the inputs."""
    historical = load_historical_data()
    n_runs, years = 10, 5
    indices = np.tile(np.arange(years, dtype=np.int32), (n_runs, 1))
    # Mix: half guaranteed-success (no spending), half guaranteed-fail (huge spending)
    spending = np.zeros((n_runs, years))
    spending[5:, :] = 1e9
    params_dict = {
        "cash_value": 100_000,
        "market_value": 0,
        "bond_value": 0,
        "earnings": 0,
        "years_to_simulate": years,
        "withdrawal_tax_rate": 0,
    }
    js_out = _run_js(
        node_bin,
        f"const params = {json.dumps(params_dict)};\n"
        f"const idx = new Int32Array({json.dumps(indices.flatten().tolist())});\n"
        f"const spend = new Float64Array({json.dumps(spending.flatten().tolist())});\n"
        f"const hist = new Float64Array({json.dumps(historical.flatten().tolist())});\n"
        "const out = ClientSim.runEngineCore(params, idx, spend, hist);\n"
        f"emit(ClientSim.computeResults(out, {n_runs}, params));",
    )
    assert 0.0 <= js_out["success_rate"] <= 1.0
    assert abs(js_out["success_rate"] - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# Partial-run output (Stop-mid-flight semantics)
# ---------------------------------------------------------------------------


def test_js_partial_results_match_full_when_k_equals_n(node_bin: str) -> None:
    historical = load_historical_data()
    n_runs, years = 20, 10
    indices = np.tile(np.arange(years, dtype=np.int32), (n_runs, 1))
    spending = np.full((n_runs, years), 5_000.0)
    params_dict = {
        "cash_value": 100_000,
        "market_value": 0,
        "bond_value": 0,
        "earnings": 0,
        "years_to_simulate": years,
        "withdrawal_tax_rate": 0,
    }
    full_and_partial = _run_js(
        node_bin,
        f"const params = {json.dumps(params_dict)};\n"
        f"const idx = new Int32Array({json.dumps(indices.flatten().tolist())});\n"
        f"const spend = new Float64Array({json.dumps(spending.flatten().tolist())});\n"
        f"const hist = new Float64Array({json.dumps(historical.flatten().tolist())});\n"
        "const out = ClientSim.runEngineCore(params, idx, spend, hist);\n"
        f"const full = ClientSim.computeResults(out, {n_runs}, params);\n"
        f"const partial = ClientSim.computeResults(out, {n_runs}, params);\n"
        "emit({full: full, partial: partial});",
    )
    assert full_and_partial["full"] == full_and_partial["partial"]


def test_js_partial_results_smaller_k_produces_valid_output(node_bin: str) -> None:
    historical = load_historical_data()
    n_runs, years = 100, 10
    rng = np.random.default_rng(0)
    starts = rng.integers(0, len(historical) - years + 1, size=n_runs).astype(np.int32)
    indices = (starts[:, None] + np.arange(years, dtype=np.int32)[None, :]).astype(np.int32)
    spending = np.full((n_runs, years), 5_000.0)
    params_dict = {
        "cash_value": 100_000,
        "market_value": 0,
        "bond_value": 0,
        "earnings": 0,
        "years_to_simulate": years,
        "withdrawal_tax_rate": 0,
    }
    js_out = _run_js(
        node_bin,
        f"const params = {json.dumps(params_dict)};\n"
        f"const idx = new Int32Array({json.dumps(indices.flatten().tolist())});\n"
        f"const spend = new Float64Array({json.dumps(spending.flatten().tolist())});\n"
        f"const hist = new Float64Array({json.dumps(historical.flatten().tolist())});\n"
        "const out = ClientSim.runEngineCore(params, idx, spend, hist);\n"
        "emit(ClientSim.computeResults(out, 25, params));",
    )
    assert len(js_out["final_year_distribution"]) == 25
    assert 0.0 <= js_out["success_rate"] <= 1.0
    for p in ("p10", "p25", "p50", "p75", "p90"):
        assert len(js_out["percentiles"][p]) == years + 1


def test_js_partial_results_k_zero_handled(node_bin: str) -> None:
    historical = load_historical_data()
    params_dict = {
        "cash_value": 1,
        "market_value": 1,
        "bond_value": 0,
        "earnings": 0,
        "years_to_simulate": 1,
        "withdrawal_tax_rate": 0,
    }
    js_out = _run_js(
        node_bin,
        f"const params = {json.dumps(params_dict)};\n"
        "const idx = new Int32Array([0]);\n"
        "const spend = new Float64Array([0]);\n"
        f"const hist = new Float64Array({json.dumps(historical.flatten().tolist())});\n"
        "const out = ClientSim.runEngineCore(params, idx, spend, hist);\n"
        "emit(ClientSim.computeResults(out, 0, params));",
    )
    assert js_out is None


# ---------------------------------------------------------------------------
# Sanity: full Python run still works (regression guard)
# ---------------------------------------------------------------------------


def test_python_engine_still_works_unchanged() -> None:
    """Guard that we haven't broken the existing Python engine."""
    historical = load_historical_data()
    params = SimulationInput(
        cash_value=100_000,
        market_value=400_000,
        bond_value=0,
        earnings=50_000,
        spending_distribution=FlatDistribution(value=60_000),
        years_to_simulate=10,
    )
    result = run_simulation(params, historical, n_runs=100, seed=42)
    assert 0.0 <= result.success_rate <= 1.0
    assert len(result.final_year_distribution) == 100
    assert len(result.year_labels) == 11
    # And the bootstrap helper still works
    rng = np.random.default_rng(0)
    idx = _build_bootstrap_indices(rng, 5, 10, 10, len(historical))
    assert idx.shape == (5, 10)


# ---------------------------------------------------------------------------
# Safe-spending solver parity
# ---------------------------------------------------------------------------


def _py_critical_multipliers(
    params: SimulationInput,
    indices: np.ndarray,
    spending: np.ndarray,
    historical: np.ndarray,
    target_net_worth: float,
) -> tuple[list[float | None], str]:
    """Python solver over injected arrays, so both sides see identical inputs."""
    from vibe_carlo.simulation import solver
    from vibe_carlo.simulation.models import COL_BOND, COL_CPI, COL_SP500

    n_runs, years = indices.shape
    total = params.cash_value + params.market_value + params.bond_value
    sampled = historical[indices]
    nominal = (params.market_value / total) * sampled[:, :, COL_SP500] + (
        params.bond_value / total
    ) * sampled[:, :, COL_BOND]
    real_returns = (1 + nominal) / (1 + sampled[:, :, COL_CPI]) - 1

    earnings = np.full((n_runs, years), params.earnings, dtype=np.float64)
    tax_divisor = np.full((n_runs, years), 1.0 / (1.0 - params.withdrawal_tax_rate))

    table = solver._solve(
        real_returns,
        spending,
        earnings,
        tax_divisor,
        slice(0, years),
        total,
        target_net_worth,
        phase_name=None,
    )
    return [row.multiplier for row in table.rows], table.method


def _solver_compare(
    node_bin: str,
    params: SimulationInput,
    indices: np.ndarray,
    spending: np.ndarray,
    historical: np.ndarray,
    target_net_worth: float = 0.0,
) -> None:
    n_runs, years = indices.shape
    js_params = {
        "cash_value": params.cash_value,
        "market_value": params.market_value,
        "bond_value": params.bond_value,
        "earnings": params.earnings,
        "years_to_simulate": params.years_to_simulate,
        "withdrawal_tax_rate": params.withdrawal_tax_rate,
    }
    js_out = _run_js(
        node_bin,
        "const idx = new Int32Array(DATA.indices);\n"
        "const spend = new Float64Array(DATA.spending);\n"
        "const hist = new Float64Array(DATA.historical);\n"
        "const solved = ClientSim.solveCriticalMultipliers(\n"
        "  DATA.params, idx, spend, hist, DATA.target\n"
        ");\n"
        "let sum = 0;\n"
        "for (let i = 0; i < spend.length; i++) sum += spend[i];\n"
        "emit(ClientSim.buildSafeSpendingTable(\n"
        "  solved.criticals, DATA.nRuns, sum / spend.length, DATA.years,\n"
        "  DATA.target, solved.refined\n"
        "));",
        data={
            "params": js_params,
            "indices": indices.flatten().tolist(),
            "spending": spending.flatten().tolist(),
            "historical": historical.flatten().tolist(),
            "target": target_net_worth,
            "nRuns": n_runs,
            "years": years,
        },
    )

    py_multipliers, py_method = _py_critical_multipliers(
        params, indices, spending, historical, target_net_worth
    )

    assert js_out["method"] == py_method
    # Also pins the JS SUCCESS_LEVELS to the Python one; the two must not drift.
    assert [row["success_pct"] for row in js_out["rows"]] == list(SUCCESS_LEVELS)
    assert abs(js_out["current_mean_spending"] - float(np.mean(spending))) < 1e-6

    for row, py_m in zip(js_out["rows"], py_multipliers):
        if py_m is None:
            assert row["multiplier"] is None
            continue
        assert row["multiplier"] is not None
        assert abs(row["multiplier"] - py_m) < 1e-9, (
            f"{row['success_pct']}%: {row['multiplier']} vs {py_m}"
        )


def _solver_fixtures(
    seed: int, n_runs: int = 400, years: int = 30
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    historical = load_historical_data()
    indices = _build_bootstrap_indices(rng, n_runs, years, 5, len(historical))
    return indices, historical


def _solver_params(
    spending: FlatDistribution | TruncatedNormalDistribution,
    earnings: float = 0.0,
    tax: float = 0.0,
) -> SimulationInput:
    return SimulationInput(
        cash_value=50_000.0,
        market_value=800_000.0,
        bond_value=150_000.0,
        earnings=earnings,
        spending_distribution=spending,
        years_to_simulate=30,
        sample_years=5,
        withdrawal_tax_rate=tax,
    )


def test_js_solver_flat_spending(node_bin: str) -> None:
    indices, historical = _solver_fixtures(seed=11)
    params = _solver_params(FlatDistribution(value=40_000))
    spending = np.full(indices.shape, 40_000.0)
    _solver_compare(node_bin, params, indices, spending, historical)


def test_js_solver_with_tax(node_bin: str) -> None:
    indices, historical = _solver_fixtures(seed=12)
    params = _solver_params(FlatDistribution(value=40_000), tax=0.22)
    spending = np.full(indices.shape, 40_000.0)
    _solver_compare(node_bin, params, indices, spending, historical)


def test_js_solver_varying_spending(node_bin: str) -> None:
    indices, historical = _solver_fixtures(seed=13)
    params = _solver_params(FlatDistribution(value=45_000), tax=0.15)
    rng = np.random.default_rng(99)
    spending = rng.uniform(30_000, 60_000, size=indices.shape)
    _solver_compare(node_bin, params, indices, spending, historical)


def test_js_solver_terminal_target(node_bin: str) -> None:
    indices, historical = _solver_fixtures(seed=14)
    params = _solver_params(FlatDistribution(value=40_000))
    spending = np.full(indices.shape, 40_000.0)
    _solver_compare(node_bin, params, indices, spending, historical, target_net_worth=500_000.0)


def test_js_solver_refinement_path(node_bin: str) -> None:
    """Earnings inside the spending range plus a tax rate forces the bisection."""
    indices, historical = _solver_fixtures(seed=15)
    params = _solver_params(FlatDistribution(value=60_000), earnings=60_000.0, tax=0.25)
    rng = np.random.default_rng(7)
    spending = rng.uniform(30_000, 90_000, size=indices.shape)
    _solver_compare(node_bin, params, indices, spending, historical)


def test_js_solver_surplus_without_tax_stays_closed_form(node_bin: str) -> None:
    indices, historical = _solver_fixtures(seed=16)
    params = _solver_params(FlatDistribution(value=60_000), earnings=60_000.0)
    rng = np.random.default_rng(8)
    spending = rng.uniform(30_000, 90_000, size=indices.shape)
    _solver_compare(node_bin, params, indices, spending, historical)


def test_js_solver_unreachable_target_is_null(node_bin: str) -> None:
    indices, historical = _solver_fixtures(seed=17, n_runs=200)
    params = _solver_params(FlatDistribution(value=40_000))
    spending = np.full(indices.shape, 40_000.0)
    _solver_compare(
        node_bin, params, indices, spending, historical, target_net_worth=500_000_000.0
    )


def test_js_solver_round_trips_through_the_js_engine(node_bin: str) -> None:
    """Solve for 90%, spend that much, and check the JS engine agrees.

    Same property the Python solver tests assert, verified end to end inside
    the browser engine rather than across the language boundary.
    """
    indices, historical = _solver_fixtures(seed=21, n_runs=2_000)
    params = _solver_params(FlatDistribution(value=40_000), tax=0.15)
    spending = np.full(indices.shape, 40_000.0)
    js_params = {
        "cash_value": params.cash_value,
        "market_value": params.market_value,
        "bond_value": params.bond_value,
        "earnings": params.earnings,
        "years_to_simulate": params.years_to_simulate,
        "withdrawal_tax_rate": params.withdrawal_tax_rate,
    }

    success = _run_js(
        node_bin,
        "const idx = new Int32Array(DATA.indices);\n"
        "const spend = new Float64Array(DATA.spending);\n"
        "const hist = new Float64Array(DATA.historical);\n"
        "const solved = ClientSim.solveCriticalMultipliers(DATA.params, idx, spend, hist, 0);\n"
        "let sum = 0;\n"
        "for (let i = 0; i < spend.length; i++) sum += spend[i];\n"
        "const table = ClientSim.buildSafeSpendingTable(\n"
        "  solved.criticals, DATA.nRuns, sum / spend.length, DATA.years, 0, solved.refined\n"
        ");\n"
        "const row = table.rows.find(function(r) { return r.success_pct === 90; });\n"
        "const scaled = new Float64Array(spend.length);\n"
        "for (let i = 0; i < spend.length; i++) scaled[i] = spend[i] * row.multiplier;\n"
        "const out = ClientSim.runEngineCore(DATA.params, idx, scaled, hist);\n"
        "emit(ClientSim.computeResults(out, DATA.nRuns, DATA.params).success_rate);",
        data={
            "params": js_params,
            "indices": indices.flatten().tolist(),
            "spending": spending.flatten().tolist(),
            "historical": historical.flatten().tolist(),
            "nRuns": indices.shape[0],
            "years": indices.shape[1],
        },
    )
    # Exact to the granularity of the run count.
    assert abs(success * 100 - 90) < 0.1


def test_js_run_batched_produces_a_safe_spending_table(node_bin: str) -> None:
    """The batched page driver accumulates per-run multipliers across batches."""
    historical = load_historical_data()
    js_params = {
        "cash_value": 50_000.0,
        "market_value": 800_000.0,
        "bond_value": 150_000.0,
        "earnings": 0.0,
        "spending_distribution": {"dist_type": "flat", "value": 40_000},
        "years_to_simulate": 30,
        "sample_years": 5,
        "withdrawal_tax_rate": 0.0,
    }
    table = _run_js(
        node_bin,
        "const hist = new Float64Array(DATA.historical);\n"
        "ClientSim.runBatched(DATA.params, hist, {\n"
        "  nRuns: 2000, batchSize: 500, seed: 42, targetNetWorth: 0,\n"
        "}).then(function(out) { emit(out.safeSpending); });",
        data={"params": js_params, "historical": historical.flatten().tolist()},
    )

    assert [row["success_pct"] for row in table["rows"]] == list(SUCCESS_LEVELS)
    assert table["method"] == "closed_form"
    assert table["solve_years"] == 30
    assert table["current_mean_spending"] == pytest.approx(40_000)

    spends = [row["annual_spending"] for row in table["rows"]]
    assert all(s is not None for s in spends)
    # Success rates descend, so the spending they allow must ascend.
    assert spends == sorted(spends)
