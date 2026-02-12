# vibe_carlo

Personal financial planning powered by Monte Carlo simulation.

Input your financial situation — portfolio, contributions, spending, asset allocation — and get a probability distribution of your financial future based on bootstrap resampling of historical market data.

## Historical Data

The simulation uses Aswath Damodaran's "Historical Returns on Stocks, Bonds and Bills" dataset from NYU Stern, covering 1928–2024. The CSV is shipped in the repo at `src/vibe_carlo/data/historical_returns.csv`.

Three series are used per year:

| Column | Source | Description |
|--------|--------|-------------|
| `sp500_return` | S&P 500 total return (including dividends) | [Damodaran dataset](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histretSP.html) |
| `bond_return` | US 10-year Treasury bond return (coupon + price change) | [Damodaran dataset](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histretSP.html) |
| `cpi_inflation` | CPI inflation rate | [FRED / Damodaran dataset](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histretSP.html) |

All values are stored as decimals (e.g., 0.10 = 10%). No external APIs are called at runtime.

## Simulation Algorithm

Each simulation request runs 10,000 Monte Carlo paths with the following procedure:

1. **Asset allocation**: Compute portfolio weights from the input dollar values:
   - `market_alloc = market_value / total_portfolio`
   - `bond_alloc = bond_value / total_portfolio`
   - `cash_alloc = cash_value / total_portfolio`

2. **Block bootstrap resampling**: For each of the 10,000 runs, sample contiguous blocks from the historical dataset. Pick a random start index such that the full block fits (`start + block_length ≤ dataset_length`). Take that block's stock return, bond return, and CPI inflation together — preserving cross-asset and asset-inflation correlations within each year. If `years_to_simulate > sample_years`, draw additional blocks and append until all years are covered.

3. **Year-by-year compounding**: For each simulated year:
   - Compute the blended nominal return: `(market_alloc × stock_return) + (bond_alloc × bond_return) + (cash_alloc × 0.0)`
   - Deflate to a real return: `real_return = (1 + nominal_return) / (1 + cpi_inflation) - 1`
   - Update the portfolio: `portfolio = portfolio × (1 + real_return) + contributions - spending`
   - Floor the portfolio at $0 (cannot go negative)

4. **Outputs**:
   - **Fan chart**: Percentile bands (10th, 25th, 50th, 75th, 90th) of portfolio value over time
   - **Success rate**: Fraction of runs where the portfolio never reached $0
   - **Histogram**: Distribution of final-year portfolio values across all 10,000 runs

All dollar outputs are in real (inflation-adjusted) terms. Contributions and spending are assumed to be in constant real dollars.

## Running Locally

```bash
uv sync --all-extras
uv run uvicorn vibe_carlo.app:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 in your browser.

## Testing

```bash
uv run pytest tests/ -v
```
