# BND backtest summary

## Dataset
- File: `backtest-reports/BTCUSDT-1d.csv` (3224 candles, 0 gaps)
- Range: 2018-01-01T00:00:00+00:00 → 2026-10-29T00:00:00+00:00
- SHA-256: `36853b94368877c58806643b858f35e4ed35a06da10e3f2317589a4299054084`

## Verdict
**No evidence of an edge.** Failed: permutation p-value < 0.05; positive out-of-sample return; still positive at 2× costs. Treat any profit above as luck or overfitting.

Out-of-sample, risk-adjusted: Sharpe 0.52 vs 0.39 for buy & hold; max drawdown 38.25% vs 52.97%; return 36.21% vs 22.02% with 57.02% average capital invested.

## Backtest: `sma_crossover`
Costs per fill: fee 0.1%, slippage 0.05%; funding 0.0%/yr on open positions; cash interest 4.0%/yr; shorts off.

**full** (2018-01-01T00:00:00+00:00 → 2026-10-29T00:00:00+00:00, risk gate: disabled_research_only)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Net profit | 72,038.00 | 48,112.28 |
| Return | 720.38% | 481.12% |
| CAGR | 26.93% | 22.06% |
| Max drawdown | 57.32% | 81.18% |
| Volatility | 43.05% | 64.03% |
| Sharpe | 0.77 | 0.64 |
| Sortino | 1.18 | 0.92 |
| Calmar | 0.47 | 0.27 |
| Expectancy per trade | 1,827.46 | 48,111.18 |
| Turnover (x equity / yr) | 8.16 | 0.25 |
| Trades | 36 | 1 |
| Time in market | 52.39% | 99.97% |
| Avg capital exposure | 52.39% | 99.97% |
| Funding paid | 0.00 | 0.00 |
| Interest earned | 6,249.50 | 1.10 |
| Entries vetoed by risk engine | 0 | 0 |

**in_sample** (2018-01-01T00:00:00+00:00 → 2024-03-05T00:00:00+00:00, risk gate: disabled_research_only)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Net profit | 50,047.06 | 37,481.19 |
| Return | 500.47% | 374.81% |
| CAGR | 33.67% | 28.69% |
| Max drawdown | 57.32% | 81.18% |
| Volatility | 46.77% | 70.34% |
| Sharpe | 0.85 | 0.72 |
| Sortino | 1.31 | 1.03 |
| Calmar | 0.59 | 0.35 |
| Expectancy per trade | 1,871.78 | 37,480.09 |
| Turnover (x equity / yr) | 8.13 | 0.56 |
| Trades | 25 | 1 |
| Time in market | 50.40% | 99.96% |
| Avg capital exposure | 50.40% | 99.96% |
| Funding paid | 0.00 | 0.00 |
| Interest earned | 3,252.54 | 1.10 |
| Entries vetoed by risk engine | 0 | 0 |

**out_of_sample** (2024-03-06T00:00:00+00:00 → 2026-10-29T00:00:00+00:00, risk gate: disabled_research_only)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Net profit | 3,621.36 | 2,202.35 |
| Return | 36.21% | 22.02% |
| CAGR | 12.37% | 7.80% |
| Max drawdown | 38.25% | 52.97% |
| Volatility | 32.77% | 46.11% |
| Sharpe | 0.52 | 0.39 |
| Sortino | 0.80 | 0.58 |
| Calmar | 0.32 | 0.15 |
| Expectancy per trade | 260.31 | 2,202.35 |
| Turnover (x equity / yr) | 8.85 | 0.64 |
| Trades | 12 | 1 |
| Time in market | 57.02% | 100.00% |
| Avg capital exposure | 57.02% | 100.00% |
| Funding paid | 0.00 | 0.00 |
| Interest earned | 497.61 | 0.00 |
| Entries vetoed by risk engine | 0 | 0 |

## Walk-forward (SMA long/flat, independent folds)
- Folds: 4, beating buy & hold: 3
- Excess return per fold: mean 47.78 pp, median 21.32 pp

## Robustness

| Period | Combos | Beat B&H | Profitable | Median return | B&H |
| --- | ---: | ---: | ---: | ---: | ---: |
| in_sample | 34 | 100% | 34 | 803.69% | 374.81% |
| out_of_sample | 34 | 21% | 22 | 6.98% | 22.02% |

**In-sample choice** fast=10, slow=200: in-sample return 1,274.71% (Sharpe 1.16); out-of-sample return -6.43% (Sharpe 0.10), rank 26 of 34.

**Permutation test** (out-of-sample, 200 shuffles): actual -6.43%, shuffled median 19.33%, 5–95% range -36.23% … 120.17%, p-value **0.697**.

| Cost multiplier | Return | Sharpe | Trades |
| ---: | ---: | ---: | ---: |
| ×1 | -6.43% | 0.10 | 7 |
| ×2 | -8.37% | 0.08 | 7 |
| ×3 | -10.28% | 0.05 | 7 |

## Walk-forward optimisation (rolling, train 1000, test 250, embargo 5)
- Folds: 8, profitable: 5
- Chained out-of-sample return: 348.29%; with switch-off after poor folds: 105.38% (2 folds skipped)
- Mean Sharpe: train 1.38 vs test 0.51 (a large gap means overfitting)
- Parameter change rate 0.86, 7 distinct sets

_Paper research only. Past results do not predict future returns._
