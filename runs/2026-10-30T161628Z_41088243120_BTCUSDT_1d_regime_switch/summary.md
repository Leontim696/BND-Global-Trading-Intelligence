# BND backtest summary

## Dataset
- File: `backtest-reports/BTCUSDT-1d.csv` (3224 candles, 0 gaps)
- Range: 2018-01-01T00:00:00+00:00 → 2026-10-29T00:00:00+00:00
- SHA-256: `36853b94368877c58806643b858f35e4ed35a06da10e3f2317589a4299054084`

## Verdict
**No evidence of an edge.** Failed: permutation p-value < 0.05; positive out-of-sample return; still positive at 2× costs. Treat any profit above as luck or overfitting.

Out-of-sample, risk-adjusted: Sharpe 0.56 vs 0.39 for buy & hold; max drawdown 38.60% vs 52.97%; return 34.46% vs 22.02% with 30.89% average capital invested.

## Backtest: `regime_switch`
Costs per fill: fee 0.1%, slippage 0.05%; funding 0.0%/yr on open positions; cash interest 4.0%/yr; shorts off.

**full** (2018-01-01T00:00:00+00:00 → 2026-10-29T00:00:00+00:00, risk gate: disabled_research_only)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Net profit | 15,205.73 | 48,112.28 |
| Return | 152.06% | 481.12% |
| CAGR | 11.04% | 22.06% |
| Max drawdown | 64.67% | 81.18% |
| Volatility | 39.64% | 64.03% |
| Sharpe | 0.47 | 0.64 |
| Sortino | 0.65 | 0.92 |
| Calmar | 0.17 | 0.27 |
| Expectancy per trade | 144.81 | 48,111.18 |
| Turnover (x equity / yr) | 17.95 | 0.25 |
| Trades | 78 | 1 |
| Time in market | 32.60% | 99.97% |
| Avg capital exposure | 32.60% | 99.97% |
| Funding paid | 0.00 | 0.00 |
| Interest earned | 3,910.19 | 1.10 |
| Entries vetoed by risk engine | 0 | 0 |

**in_sample** (2018-01-01T00:00:00+00:00 → 2024-03-05T00:00:00+00:00, risk gate: disabled_research_only)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Net profit | 8,689.66 | 37,481.19 |
| Return | 86.90% | 374.81% |
| CAGR | 10.66% | 28.69% |
| Max drawdown | 64.67% | 81.18% |
| Volatility | 44.23% | 70.34% |
| Sharpe | 0.46 | 0.72 |
| Sortino | 0.63 | 1.03 |
| Calmar | 0.16 | 0.35 |
| Expectancy per trade | 122.91 | 37,480.09 |
| Turnover (x equity / yr) | 18.02 | 0.56 |
| Trades | 55 | 1 |
| Time in market | 33.33% | 99.96% |
| Avg capital exposure | 33.33% | 99.96% |
| Funding paid | 0.00 | 0.00 |
| Interest earned | 1,929.59 | 1.10 |
| Entries vetoed by risk engine | 0 | 0 |

**out_of_sample** (2024-03-06T00:00:00+00:00 → 2026-10-29T00:00:00+00:00, risk gate: disabled_research_only)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Net profit | 3,446.06 | 2,202.35 |
| Return | 34.46% | 22.02% |
| CAGR | 11.82% | 7.80% |
| Max drawdown | 38.60% | 52.97% |
| Volatility | 25.98% | 46.11% |
| Sharpe | 0.56 | 0.39 |
| Sortino | 0.84 | 0.58 |
| Calmar | 0.31 | 0.15 |
| Expectancy per trade | 99.56 | 2,202.35 |
| Turnover (x equity / yr) | 18.40 | 0.64 |
| Trades | 24 | 1 |
| Time in market | 30.89% | 100.00% |
| Avg capital exposure | 30.89% | 100.00% |
| Funding paid | 0.00 | 0.00 |
| Interest earned | 1,056.56 | 0.00 |
| Entries vetoed by risk engine | 0 | 0 |

## Walk-forward (SMA long/flat, independent folds)
- Folds: 4, beating buy & hold: 3
- Excess return per fold: mean 47.78 pp, median 21.32 pp

## Robustness

| Period | Combos | Beat B&H | Profitable | Median return | B&H |
| --- | ---: | ---: | ---: | ---: | ---: |
| in_sample | 9 | 56% | 9 | 391.99% | 374.81% |
| out_of_sample | 9 | 67% | 8 | 23.80% | 22.02% |

**In-sample choice** window=20, trend_level=0.3: in-sample return 919.76% (Sharpe 1.13); out-of-sample return -23.22% (Sharpe -0.21), rank 9 of 9.

**Permutation test** (out-of-sample, 200 shuffles): actual -23.22%, shuffled median 8.96%, 5–95% range -41.85% … 81.26%, p-value **0.821**.

| Cost multiplier | Return | Sharpe | Trades |
| ---: | ---: | ---: | ---: |
| ×1 | -23.22% | -0.21 | 41 |
| ×2 | -32.10% | -0.37 | 41 |
| ×3 | -39.96% | -0.53 | 41 |

## Walk-forward optimisation (rolling, train 1000, test 250, embargo 5)
- Folds: 8, profitable: 6, beating buy & hold: 2
- Chained out-of-sample return: 115.19% vs buy & hold 548.67% on the same windows; with switch-off after poor folds: 49.10% (2 folds skipped)
- Mean Sharpe: train 1.24 vs test 0.49 (a large gap means overfitting)
- Parameter change rate 0.57, 5 distinct sets

_Paper research only. Past results do not predict future returns._
