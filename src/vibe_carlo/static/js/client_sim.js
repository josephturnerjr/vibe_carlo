/**
 * Client-side Monte Carlo simulation engine.
 *
 * Direct transliteration of:
 *   src/vibe_carlo/simulation/engine.py
 *   src/vibe_carlo/simulation/tax.py
 *   src/vibe_carlo/simulation/distributions.py
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
    // Tax constants — mirror simulation/tax.py exactly.
    // -----------------------------------------------------------------------

    const TAX_RATES = [0.10, 0.12, 0.22, 0.24, 0.32, 0.35, 0.37];

    const TAX_BRACKETS = {
        single:             [12400,  50400, 105700, 201775, 256225, 640600, Infinity],
        married_jointly:    [24800, 100800, 211400, 403550, 512450, 768700, Infinity],
        married_separately: [12400,  50400, 105700, 201775, 256225, 384350, Infinity],
        head_of_household:  [17700,  67450, 105700, 201750, 256200, 640600, Infinity],
    };

    const STANDARD_DEDUCTION = {
        single: 16100.0,
        married_jointly: 32200.0,
        married_separately: 16100.0,
        head_of_household: 24150.0,
    };

    function grossUpWithdrawal(desiredSpending, filingStatus) {
        if (desiredSpending <= 0) return 0.0;
        const stdDed = STANDARD_DEDUCTION[filingStatus];
        const brackets = TAX_BRACKETS[filingStatus];
        let afterTaxRemaining = desiredSpending;
        let gross = 0.0;

        if (stdDed > 0 && afterTaxRemaining > 0) {
            const use = Math.min(stdDed, afterTaxRemaining);
            gross += use;
            afterTaxRemaining -= use;
        }
        if (afterTaxRemaining <= 0) return gross;

        let prevBound = 0.0;
        for (let i = 0; i < TAX_RATES.length; i++) {
            if (afterTaxRemaining <= 0) break;
            const rate = TAX_RATES[i];
            const upper = brackets[i];
            const bracketCapacity = upper - prevBound;
            const afterTaxPerDollar = 1.0 - rate;
            const afterTaxCapacity = bracketCapacity * afterTaxPerDollar;

            if (afterTaxRemaining <= afterTaxCapacity) {
                gross += afterTaxRemaining / afterTaxPerDollar;
                afterTaxRemaining = 0.0;
            } else {
                gross += bracketCapacity;
                afterTaxRemaining -= afterTaxCapacity;
            }
            prevBound = upper;
        }
        return gross;
    }

    function grossUpWithdrawalArray(desiredSpending, filingStatus) {
        const stdDed = STANDARD_DEDUCTION[filingStatus];
        const brackets = TAX_BRACKETS[filingStatus];
        const n = desiredSpending.length;
        const afterTaxRemaining = new Float64Array(n);
        for (let i = 0; i < n; i++) {
            // Match Python: clamp negatives to 0 in phase-1 use; here we mirror
            // the `np.maximum(use, 0.0)` after standard deduction by clamping
            // remaining to 0 when negative below.
            afterTaxRemaining[i] = desiredSpending[i];
        }
        const gross = new Float64Array(n);

        if (stdDed > 0) {
            for (let i = 0; i < n; i++) {
                let use = Math.min(stdDed, afterTaxRemaining[i]);
                if (use < 0) use = 0;
                gross[i] += use;
                afterTaxRemaining[i] -= use;
            }
        }

        let prevBound = 0.0;
        for (let r = 0; r < TAX_RATES.length; r++) {
            const rate = TAX_RATES[r];
            const upper = brackets[r];
            const bracketCapacity = upper - prevBound;
            const afterTaxPerDollar = 1.0 - rate;
            const afterTaxCapacity = bracketCapacity * afterTaxPerDollar;
            for (let i = 0; i < n; i++) {
                let canFill = Math.min(afterTaxRemaining[i], afterTaxCapacity);
                if (canFill < 0) canFill = 0;
                gross[i] += canFill / afterTaxPerDollar;
                afterTaxRemaining[i] -= canFill;
            }
            prevBound = upper;
        }
        return gross;
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
    //             filing_status (string|null), years_to_simulate }
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

        const grossWithdrawals = params.filing_status
            ? grossUpWithdrawalArray(shortfall, params.filing_status)
            : shortfall;

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
        if (params.filing_status) {
            const cells = k * years;
            let gSum = 0, sSum = 0;
            for (let i = 0; i < cells; i++) {
                gSum += grossWithdrawals[i];
                sSum += shortfall[i];
            }
            const meanGross = gSum / cells;
            const meanShortfall = sSum / cells;
            grossWithdrawal = meanGross;
            effectiveTaxRate = meanGross > 0 ? (meanGross - meanShortfall) / meanGross : 0.0;
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
    // Page driver — batched execution with onProgress / abort support.
    // -----------------------------------------------------------------------

    async function runBatched(params, historicalData, options) {
        const {
            nRuns = 10000,
            batchSize = 500,
            seed = null,
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

        let kCompleted = 0;
        for (let i = 0; i < nRuns; i += batchSize) {
            const batchEnd = Math.min(i + batchSize, nRuns);
            const batchN = batchEnd - i;

            const spending = sampleSpending(params.spending_distribution, batchN, years, rng);
            const indices = buildBootstrapIndices(rng, batchN, years, blockLen, nHistorical);

            const batchOut = runEngineCore(params, indices, spending, historicalData);

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
        return {
            result: computeResults(engineOut, kCompleted, params),
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
        const filingStatus = str('filing_status') || null;
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
                filing_status: filingStatus,
            },
            errors: errors,
        };
    }

    // -----------------------------------------------------------------------
    // Exports
    // -----------------------------------------------------------------------

    const ClientSim = {
        // Constants
        TAX_RATES, TAX_BRACKETS, STANDARD_DEDUCTION,
        // PRNG
        makeRng,
        // Tax
        grossUpWithdrawal, grossUpWithdrawalArray,
        // Sampling
        sampleFlat, sampleUniform, sampleTruncatedNormal, sampleSpending,
        // Bootstrap
        buildBootstrapIndices,
        // Engine
        runEngineCore, computeResults,
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
