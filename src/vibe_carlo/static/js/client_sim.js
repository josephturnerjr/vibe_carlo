/**
 * Client-side Monte Carlo simulation engine.
 *
 * Direct transliteration of:
 *   src/vibe_carlo/simulation/engine.py
 *   src/vibe_carlo/simulation/distributions.py
 *   src/vibe_carlo/simulation/solver.py
 *
 * Exposes pure functions so the parity tests (Node) can import them, plus a
 * batched driver for the page (with progress + Stop callback support).
 *
 * Dual-exported: attaches `ClientSim` to globalThis (for the browser) and
 * sets `module.exports = ClientSim` (for Node).
 */

(function() {
    'use strict';

    // -----------------------------------------------------------------------
    // PRNG: mulberry32 (seedable, deterministic). Used for parity testing.
    // The page driver seeds from Math.random() if no seed is provided.
    // -----------------------------------------------------------------------

    function makeRng(seed) {
        let s = (seed === undefined || seed === null)
            ? (Math.random() * 4294967296) >>> 0
            : (seed >>> 0);
        return function() {
            s |= 0; s = (s + 0x6D2B79F5) | 0;
            let t = Math.imul(s ^ (s >>> 15), 1 | s);
            t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
            return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
        };
    }

    // -----------------------------------------------------------------------
    // Distribution sampling — mirror simulation/distributions.py.
    // Returns Float64Array of length nRuns*years (row-major).
    // -----------------------------------------------------------------------

    function sampleFlat(value, nRuns, years) {
        const out = new Float64Array(nRuns * years);
        out.fill(value);
        return out;
    }

    function sampleUniform(low, high, nRuns, years, rng) {
        const total = nRuns * years;
        const out = new Float64Array(total);
        const range = high - low;
        for (let i = 0; i < total; i++) out[i] = low + rng() * range;
        return out;
    }

    function sampleTruncatedNormal(low, high, mean, stddev, nRuns, years, rng) {
        const total = nRuns * years;
        const out = new Float64Array(total);
        let filled = 0;
        // Box-Muller produces two normals per iteration; use both.
        while (filled < total) {
            let u1 = rng();
            while (u1 === 0) u1 = rng();
            const u2 = rng();
            const r = Math.sqrt(-2 * Math.log(u1));
            const theta = 2 * Math.PI * u2;
            const z1 = r * Math.cos(theta);
            const z2 = r * Math.sin(theta);
            const c1 = mean + z1 * stddev;
            if (c1 >= low && c1 <= high) {
                out[filled++] = c1;
                if (filled >= total) break;
            }
            const c2 = mean + z2 * stddev;
            if (c2 >= low && c2 <= high) {
                out[filled++] = c2;
            }
        }
        return out;
    }

    function sampleSpending(dist, nRuns, years, rng) {
        if (dist.dist_type === 'flat') return sampleFlat(dist.value, nRuns, years);
        if (dist.dist_type === 'uniform') return sampleUniform(dist.low, dist.high, nRuns, years, rng);
        if (dist.dist_type === 'truncated_normal') {
            return sampleTruncatedNormal(dist.low, dist.high, dist.mean, dist.stddev, nRuns, years, rng);
        }
        throw new Error('Unknown distribution type: ' + dist.dist_type);
    }

    // -----------------------------------------------------------------------
    // Block bootstrap — mirror engine._build_bootstrap_indices.
    // Returns Int32Array of length nRuns*years (row-major).
    // -----------------------------------------------------------------------

    function buildBootstrapIndices(rng, nRuns, years, blockLen, nHistorical) {
        const maxStart = nHistorical - blockLen;
        const indices = new Int32Array(nRuns * years);
        let col = 0;
        while (col < years) {
            const remaining = years - col;
            const currentBlock = Math.min(blockLen, remaining);
            for (let r = 0; r < nRuns; r++) {
                const start = Math.floor(rng() * (maxStart + 1));
                for (let off = 0; off < currentBlock; off++) {
                    indices[r * years + col + off] = start + off;
                }
            }
            col += currentBlock;
        }
        return indices;
    }

    // -----------------------------------------------------------------------
    // Engine core — pure (no RNG) given pre-sampled inputs.
    // Mirrors the vectorized loop in engine.run_simulation.
    //
    // Inputs:
    //   params: { cash_value, market_value, bond_value, earnings,
    //             withdrawal_tax_rate (0..1), years_to_simulate }
    //   indicesFlat:  Int32Array(nRuns*years), historical-row indices
    //   spendingFlat: Float64Array(nRuns*years), per-run-per-year spending dollars
    //   historicalData: Float64Array(nHistorical*3) row-major [sp500, bond, cpi]
    //
    // Returns:
    //   { portfolios:        Float64Array(nRuns*(years+1)),   row-major
    //     everHitZero:       Uint8Array(nRuns),
    //     grossWithdrawals:  Float64Array(nRuns*years),
    //     shortfall:         Float64Array(nRuns*years) }
    // -----------------------------------------------------------------------

    function runEngineCore(params, indicesFlat, spendingFlat, historicalData) {
        const years = params.years_to_simulate;
        const nRuns = indicesFlat.length / years;
        if (!Number.isInteger(nRuns)) {
            throw new Error('indicesFlat length not divisible by years');
        }

        const totalPortfolio = params.cash_value + params.market_value + params.bond_value;
        const marketAlloc = params.market_value / totalPortfolio;
        const bondAlloc = params.bond_value / totalPortfolio;
        const earnings = params.earnings;

        const total = nRuns * years;
        const shortfall = new Float64Array(total);
        const surplus = new Float64Array(total);
        for (let i = 0; i < total; i++) {
            const diff = spendingFlat[i] - earnings;
            if (diff > 0) {
                shortfall[i] = diff;
            } else {
                surplus[i] = -diff;
            }
        }

        const taxRate = params.withdrawal_tax_rate || 0;
        let grossWithdrawals;
        if (taxRate > 0) {
            const scale = 1.0 / (1.0 - taxRate);
            grossWithdrawals = new Float64Array(total);
            for (let i = 0; i < total; i++) grossWithdrawals[i] = shortfall[i] * scale;
        } else {
            grossWithdrawals = shortfall;
        }

        const portfolios = new Float64Array(nRuns * (years + 1));
        const everHitZero = new Uint8Array(nRuns);

        for (let r = 0; r < nRuns; r++) {
            const portRow = r * (years + 1);
            portfolios[portRow] = totalPortfolio;
            let value = totalPortfolio;
            let hitZero = false;
            const idxBase = r * years;
            for (let y = 0; y < years; y++) {
                const histIdx = indicesFlat[idxBase + y];
                const dataIdx = histIdx * 3;
                const sp500 = historicalData[dataIdx];
                const bond = historicalData[dataIdx + 1];
                const cpi = historicalData[dataIdx + 2];
                const nominal = marketAlloc * sp500 + bondAlloc * bond;
                const real = (1 + nominal) / (1 + cpi) - 1;
                const idx = idxBase + y;
                value = value * (1 + real) + surplus[idx] - grossWithdrawals[idx];
                if (value < 0) value = 0;
                portfolios[portRow + y + 1] = value;
                if (value === 0) hitZero = true;
            }
            if (hitZero) everHitZero[r] = 1;
        }

        return { portfolios, everHitZero, grossWithdrawals, shortfall };
    }

    // -----------------------------------------------------------------------
    // computeResults — turn engine outputs into the SimulationResult shape.
    // Uses only the first k runs (for partial-run / Stop support).
    // Returns null when k === 0.
    //
    // Percentile algorithm matches numpy.percentile default (linear interpolation).
    // -----------------------------------------------------------------------

    function _percentile(sorted, p) {
        const n = sorted.length;
        if (n === 1) return sorted[0];
        const i = (p / 100) * (n - 1);
        const lo = Math.floor(i);
        const hi = Math.ceil(i);
        if (lo === hi) return sorted[lo];
        return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
    }

    function computeResults(engineOut, k, params) {
        if (k <= 0) return null;
        const { portfolios, everHitZero, grossWithdrawals, shortfall } = engineOut;
        const years = params.years_to_simulate;

        const yearLabels = [];
        for (let y = 0; y <= years; y++) yearLabels.push(y);

        const percentiles = { p10: [], p25: [], p50: [], p75: [], p90: [] };
        const col = new Float64Array(k);
        for (let y = 0; y <= years; y++) {
            for (let r = 0; r < k; r++) col[r] = portfolios[r * (years + 1) + y];
            const sorted = Float64Array.from(col).sort();
            percentiles.p10.push(_percentile(sorted, 10));
            percentiles.p25.push(_percentile(sorted, 25));
            percentiles.p50.push(_percentile(sorted, 50));
            percentiles.p75.push(_percentile(sorted, 75));
            percentiles.p90.push(_percentile(sorted, 90));
        }

        let zeroCount = 0;
        for (let r = 0; r < k; r++) if (everHitZero[r]) zeroCount++;
        const successRate = 1.0 - zeroCount / k;

        const finalDist = new Array(k);
        for (let r = 0; r < k; r++) finalDist[r] = portfolios[r * (years + 1) + years];

        let grossWithdrawal = null;
        let effectiveTaxRate = null;
        const taxRate = params.withdrawal_tax_rate || 0;
        if (taxRate > 0) {
            const cells = k * years;
            let gSum = 0;
            for (let i = 0; i < cells; i++) gSum += grossWithdrawals[i];
            grossWithdrawal = gSum / cells;
            effectiveTaxRate = taxRate;
        }

        return {
            year_labels: yearLabels,
            percentiles: percentiles,
            success_rate: successRate,
            final_year_distribution: finalDist,
            gross_withdrawal: grossWithdrawal,
            effective_tax_rate: effectiveTaxRate,
        };
    }

    // -----------------------------------------------------------------------
    // Safe-spending solver — mirror simulation/solver.py.
    //
    // Each run gets an exact critical spending multiplier: the most it could
    // have spent and still finished solvent (and above targetNetWorth). The
    // success rate at multiplier m is then the fraction of runs with
    // m* >= m, so the answer at any success rate is a quantile of m*.
    //
    // Solves the whole horizon, which is the single-parameter-set case on the
    // Python side; plans (which solve only their final phase) are server-side.
    // -----------------------------------------------------------------------

    // Must stay identical to solver.SUCCESS_LEVELS. The 100% row is the
    // q=0.0 quantile — the single worst sampled path, so the noisiest row.
    const SUCCESS_LEVELS = [100, 95, 90, 85, 80, 75, 70, 65, 60, 55, 50];

    const REFINE_ITERATIONS = 60;
    const BRACKET_EXPANSIONS = 20;

    function solveCriticalMultipliers(params, indicesFlat, spendingFlat, historicalData, targetNetWorth) {
        const years = params.years_to_simulate;
        const nRuns = indicesFlat.length / years;
        if (!Number.isInteger(nRuns)) {
            throw new Error('indicesFlat length not divisible by years');
        }
        const target = targetNetWorth || 0;

        const totalPortfolio = params.cash_value + params.market_value + params.bond_value;
        const marketAlloc = params.market_value / totalPortfolio;
        const bondAlloc = params.bond_value / totalPortfolio;
        const earnings = params.earnings;
        const taxRate = params.withdrawal_tax_rate || 0;
        const taxDivisor = 1.0 / (1.0 - taxRate);
        const constFlow = -earnings * taxDivisor;

        const criticals = new Float64Array(nRuns);
        // Kept so the refinement pass does not recompute them.
        const realReturns = new Float64Array(nRuns * years);

        for (let r = 0; r < nRuns; r++) {
            const base = r * years;
            let growth = 1.0;      // A_n, cumulative growth through year n
            let constPart = 0.0;   // C_n, discounted sum of the m-independent flows
            let linearPart = 0.0;  // L_n, discounted sum of the per-unit-m flows
            let bound = Infinity;
            let failsRegardless = false;

            for (let y = 0; y < years; y++) {
                const dataIdx = indicesFlat[base + y] * 3;
                const nominal = marketAlloc * historicalData[dataIdx]
                    + bondAlloc * historicalData[dataIdx + 1];
                const real = (1 + nominal) / (1 + historicalData[dataIdx + 2]) - 1;
                realReturns[base + y] = real;

                growth *= (1 + real);
                const discount = 1.0 / growth;
                constPart += constFlow * discount;
                linearPart += (spendingFlat[base + y] * taxDivisor) * discount;

                // Surviving year n needs G_n < P0.
                const headroom = totalPortfolio - constPart;
                if (linearPart > 0) {
                    const b = headroom / linearPart;
                    if (b < bound) bound = b;
                } else if (headroom <= 0) {
                    failsRegardless = true;
                }

                if (y === years - 1) {
                    // Ending above the target is one more bound of the same form.
                    const terminalHeadroom = headroom - target / growth;
                    if (linearPart > 0) {
                        const tb = terminalHeadroom / linearPart;
                        if (tb < bound) bound = tb;
                    } else if (terminalHeadroom < 0) {
                        failsRegardless = true;
                    }
                }
            }

            criticals[r] = (failsRegardless || bound <= 0) ? -Infinity : bound;
        }

        // The closed form assumed every year withdraws. A surplus year only
        // breaks that when a gross-up applies to it: at a zero tax rate the
        // divisor is 1 and `shortfall * 1 - surplus` already equals the linear
        // `spending - earnings`, so the closed form stays exact.
        let hasSurplus = false;
        if (taxDivisor !== 1.0) {
            for (let r = 0; r < nRuns && !hasSurplus; r++) {
                const m = Number.isFinite(criticals[r]) ? criticals[r] : 0.0;
                const base = r * years;
                for (let y = 0; y < years; y++) {
                    if (m * spendingFlat[base + y] < earnings) { hasSurplus = true; break; }
                }
            }
        }

        if (hasSurplus) {
            // survives() is monotone decreasing in m, so bisect each run against
            // the exact clamped recursion.
            const survives = function(r, m) {
                const base = r * years;
                let value = totalPortfolio;
                let alive = true;
                for (let y = 0; y < years; y++) {
                    const diff = m * spendingFlat[base + y] - earnings;
                    const flow = diff > 0 ? diff * taxDivisor : diff;
                    value = value * (1 + realReturns[base + y]) - flow;
                    if (value < 0) value = 0;
                    if (!(value > 0)) alive = false;
                }
                return alive && value >= target;
            };

            for (let r = 0; r < nRuns; r++) {
                const seed = criticals[r];
                let low = 0.0;
                let high = Number.isFinite(seed) ? Math.max(seed, 1e-9) : 1e-9;

                // The closed form is optimistic, so `high` normally already
                // fails; expand for the rare run where it does not.
                for (let i = 0; i < BRACKET_EXPANSIONS; i++) {
                    if (!survives(r, high)) break;
                    high *= 2.0;
                }

                if (!survives(r, low)) {
                    criticals[r] = -Infinity;
                    continue;
                }
                for (let i = 0; i < REFINE_ITERATIONS; i++) {
                    const mid = 0.5 * (low + high);
                    if (survives(r, mid)) { low = mid; } else { high = mid; }
                }
                criticals[r] = low;
            }
        }

        return { criticals: criticals, refined: hasSurplus };
    }

    // numpy.quantile's default linear interpolation, including its lerp, so the
    // table lands on the same values as the Python solver.
    function _quantile(sorted, q) {
        const n = sorted.length;
        if (n === 1) return sorted[0];
        const i = q * (n - 1);
        const lo = Math.floor(i);
        const hi = Math.ceil(i);
        if (lo === hi) return sorted[lo];
        const a = sorted[lo];
        const b = sorted[hi];
        const t = i - lo;
        const diff = b - a;
        return t >= 0.5 ? b - diff * (1 - t) : a + diff * t;
    }

    function buildSafeSpendingTable(criticals, k, basisMean, solveYears, targetNetWorth, refined) {
        if (k <= 0 || !(basisMean > 0)) return null;
        const sorted = Float64Array.from(criticals.subarray(0, k)).sort();

        const rows = SUCCESS_LEVELS.map(function(level) {
            // Runs that fail at any spending level carry -Infinity; interpolating
            // between two of those is NaN, which the finiteness check catches.
            const value = _quantile(sorted, 1.0 - level / 100.0);
            if (Number.isFinite(value) && value > 0) {
                return {
                    success_pct: level,
                    multiplier: value,
                    annual_spending: value * basisMean,
                };
            }
            return { success_pct: level, multiplier: null, annual_spending: null };
        });

        return {
            rows: rows,
            target_net_worth: targetNetWorth || 0,
            current_mean_spending: basisMean,
            solve_years: solveYears,
            phase_name: null,
            method: refined ? 'refined' : 'closed_form',
        };
    }

    // -----------------------------------------------------------------------
    // Page driver — batched execution with onProgress / abort support.
    // -----------------------------------------------------------------------

    async function runBatched(params, historicalData, options) {
        const {
            nRuns = 10000,
            batchSize = 500,
            seed = null,
            targetNetWorth = 0,
            onProgress = () => {},
            shouldAbort = () => false,
        } = options || {};
        const rng = makeRng(seed);
        const years = params.years_to_simulate;
        const blockLen = params.sample_years || params.years_to_simulate;
        const nHistorical = historicalData.length / 3;

        // Pre-allocate full-size accumulators; we only fill rows up to kCompleted.
        const portfolios = new Float64Array(nRuns * (years + 1));
        const everHitZero = new Uint8Array(nRuns);
        const grossWithdrawalsAll = new Float64Array(nRuns * years);
        const shortfallAll = new Float64Array(nRuns * years);
        // The critical multiplier is per-run, so batching it needs no more than
        // concatenation — the same pass yields the simulation and the table.
        const criticalsAll = new Float64Array(nRuns);
        let spendingSum = 0;
        let spendingCells = 0;
        let refinedAny = false;

        let kCompleted = 0;
        for (let i = 0; i < nRuns; i += batchSize) {
            const batchEnd = Math.min(i + batchSize, nRuns);
            const batchN = batchEnd - i;

            const spending = sampleSpending(params.spending_distribution, batchN, years, rng);
            const indices = buildBootstrapIndices(rng, batchN, years, blockLen, nHistorical);

            const batchOut = runEngineCore(params, indices, spending, historicalData);
            const solved = solveCriticalMultipliers(
                params, indices, spending, historicalData, targetNetWorth
            );
            criticalsAll.set(solved.criticals, i);
            refinedAny = refinedAny || solved.refined;
            for (let j = 0; j < spending.length; j++) spendingSum += spending[j];
            spendingCells += spending.length;

            // Copy batch outputs into the global accumulators at offset `i`.
            portfolios.set(batchOut.portfolios, i * (years + 1));
            everHitZero.set(batchOut.everHitZero, i);
            grossWithdrawalsAll.set(batchOut.grossWithdrawals, i * years);
            shortfallAll.set(batchOut.shortfall, i * years);

            kCompleted = batchEnd;
            onProgress(kCompleted, nRuns);

            // Yield to the event loop so the UI stays responsive and Stop is processed.
            await new Promise(function(resolve) { setTimeout(resolve, 0); });
            if (shouldAbort()) break;
        }

        const engineOut = {
            portfolios: portfolios,
            everHitZero: everHitZero,
            grossWithdrawals: grossWithdrawalsAll,
            shortfall: shortfallAll,
        };
        const basisMean = spendingCells > 0 ? spendingSum / spendingCells : 0;
        return {
            result: computeResults(engineOut, kCompleted, params),
            safeSpending: buildSafeSpendingTable(
                criticalsAll, kCompleted, basisMean, years, targetNetWorth, refinedAny
            ),
            kCompleted: kCompleted,
            nRuns: nRuns,
        };
    }

    // -----------------------------------------------------------------------
    // Form parsing + validation — mirror the server-side _parse_form_params /
    // SimulationInput validators.
    // -----------------------------------------------------------------------

    function parseFormParams(form) {
        const data = new FormData(form);
        const num = function(key, dflt) {
            const v = data.get(key);
            if (v === null || v === '') return dflt;
            const n = parseFloat(v);
            return Number.isFinite(n) ? n : dflt;
        };
        const str = function(key) {
            const v = data.get(key);
            return v === null ? '' : String(v);
        };

        const cash = num('cash_value', 0);
        const market = num('market_value', 0);
        const bond = num('bond_value', 0);
        const earnings = num('earnings', 0);
        const years = num('years_to_simulate', 30);
        // Form field is a percentage (0-50); internally we store a fraction (0-0.5).
        const taxRatePct = num('withdrawal_tax_rate_pct', 0);
        const withdrawalTaxRate = taxRatePct / 100;
        const targetNetWorth = num('target_net_worth', 0);
        const distType = str('spending_dist_type') || 'flat';

        let spendingDist;
        if (distType === 'uniform') {
            spendingDist = {
                dist_type: 'uniform',
                low: num('spending_dist_low', 0),
                high: num('spending_dist_high', 0),
            };
        } else if (distType === 'truncated_normal') {
            spendingDist = {
                dist_type: 'truncated_normal',
                low: num('spending_dist_low', 0),
                high: num('spending_dist_high', 0),
                mean: num('spending_dist_mean', 0),
                stddev: num('spending_dist_stddev', 5000),
            };
        } else {
            spendingDist = { dist_type: 'flat', value: num('spending_dist_value', 0) };
        }

        const errors = [];
        if (cash < 0 || market < 0 || bond < 0) errors.push('Dollar values must be non-negative');
        if (cash + market + bond <= 0) errors.push('Total portfolio value must be greater than zero');
        if (earnings < 0) errors.push('Earnings must be non-negative');
        if (years <= 0) errors.push('Years to simulate must be positive');
        if (withdrawalTaxRate < 0 || withdrawalTaxRate >= 1) {
            errors.push('Withdrawal tax rate must be between 0% and 100%');
        }
        if (targetNetWorth < 0) errors.push('Target net worth must be non-negative');
        if (spendingDist.dist_type === 'uniform' || spendingDist.dist_type === 'truncated_normal') {
            if (spendingDist.low > spendingDist.high) errors.push('Spending: low must be ≤ high');
        }
        if (spendingDist.dist_type === 'truncated_normal') {
            if (!(spendingDist.low <= spendingDist.mean && spendingDist.mean <= spendingDist.high)) {
                errors.push('Spending: mean must be within [low, high]');
            }
            if (spendingDist.stddev <= 0) errors.push('Spending: stddev must be positive');
        }

        return {
            params: {
                cash_value: cash,
                market_value: market,
                bond_value: bond,
                earnings: earnings,
                spending_distribution: spendingDist,
                years_to_simulate: Math.floor(years),
                withdrawal_tax_rate: withdrawalTaxRate,
            },
            targetNetWorth: targetNetWorth,
            errors: errors,
        };
    }

    // -----------------------------------------------------------------------
    // Exports
    // -----------------------------------------------------------------------

    const ClientSim = {
        // PRNG
        makeRng,
        // Sampling
        sampleFlat, sampleUniform, sampleTruncatedNormal, sampleSpending,
        // Bootstrap
        buildBootstrapIndices,
        // Engine
        runEngineCore, computeResults,
        // Solver
        SUCCESS_LEVELS, solveCriticalMultipliers, buildSafeSpendingTable,
        // Driver
        runBatched,
        // Form
        parseFormParams,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = ClientSim;
    }
    if (typeof globalThis !== 'undefined') {
        globalThis.ClientSim = ClientSim;
    }
})();
