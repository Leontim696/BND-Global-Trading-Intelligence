Latest run: `runs/2026-10-31T055238Z_41174278661_BTCUSDT_1d_sma_crossover` (source 583f62c, job success)

# BND backtest summary

## Dataset
- File: `backtest-reports/BTCUSDT-1d.csv` (3225 candles, 0 gaps)
- Range: 2018-01-01T00:00:00+00:00 → 2026-10-30T00:00:00+00:00
- SHA-256: `8a0870a4a8f2fefdab6815b63541fbfa9525796e187e6017627cada068382256`

## Verdict
**No evidence of an edge.** Failed: permutation p-value < 0.05; positive out-of-sample return; still positive at 2× costs. Treat any profit above as luck or overfitting.

Out-of-sample, risk-adjusted: Sharpe 0.48 vs 0.36 for buy & hold; max drawdown 38.25% vs 52.97%; return 31.38% vs 16.74% with 56.92% average capital invested.

## Backtest: `sma_crossover`
Costs per fill: fee 0.1%, slippage 0.05%; funding 0.0%/yr on open positions; cash interest 4.0%/yr; shorts off.

**full** (2018-01-01T00:00:00+00:00 → 2026-10-30T00:00:00+00:00, risk gate: disabled_research_only)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Net profit | 72,046.99 | 47,647.99 |
| Return | 720.47% | 476.48% |
| CAGR | 26.92% | 21.94% |
| Max drawdown | 57.32% | 81.18% |
| Volatility | 43.04% | 64.02% |
| Sharpe | 0.77 | 0.63 |
| Sortino | 1.18 | 0.92 |
| Calmar | 0.47 | 0.27 |
| Expectancy per trade | 1,827.46 | 47,646.89 |
| Turnover (x equity / yr) | 8.15 | 0.25 |
| Trades | 36 | 1 |
| Time in market | 52.37% | 99.97% |
| Avg capital exposure | 52.37% | 99.97% |
| Funding paid | 0.00 | 0.00 |
| Interest earned | 6,258.48 | 1.10 |
| Entries vetoed by risk engine | 0 | 0 |

**in_sample** (2018-01-01T00:00:00+00:00 → 2024-03-06T00:00:00+00:00, risk gate: disabled_research_only)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Net profit | 52,261.49 | 39,232.21 |
| Return | 522.61% | 392.32% |
| CAGR | 34.44% | 29.43% |
| Max drawdown | 57.32% | 81.18% |
| Volatility | 46.78% | 70.33% |
| Sharpe | 0.87 | 0.73 |
| Sortino | 1.32 | 1.04 |
| Calmar | 0.60 | 0.36 |
| Expectancy per trade | 1,960.36 | 39,231.11 |
| Turnover (x equity / yr) | 8.13 | 0.57 |
| Trades | 25 | 1 |
| Time in market | 50.42% | 99.96% |
| Avg capital exposure | 50.42% | 99.96% |
| Funding paid | 0.00 | 0.00 |
| Interest earned | 3,252.54 | 1.10 |
| Entries vetoed by risk engine | 0 | 0 |

**out_of_sample** (2024-03-07T00:00:00+00:00 → 2026-10-30T00:00:00+00:00, risk gate: disabled_research_only)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Net profit | 3,138.33 | 1,674.33 |
| Return | 31.38% | 16.74% |
| CAGR | 10.85% | 6.02% |
| Max drawdown | 38.25% | 52.97% |
| Volatility | 32.70% | 46.06% |
| Sharpe | 0.48 | 0.36 |
| Sortino | 0.73 | 0.53 |
| Calmar | 0.28 | 0.11 |
| Expectancy per trade | 221.42 | 1,674.33 |
| Turnover (x equity / yr) | 8.86 | 0.65 |
| Trades | 12 | 1 |
| Time in market | 56.92% | 100.00% |
| Avg capital exposure | 56.92% | 100.00% |
| Funding paid | 0.00 | 0.00 |
| Interest earned | 481.35 | 0.00 |
| Entries vetoed by risk engine | 0 | 0 |

## Walk-forward (SMA long/flat, independent folds)
- Folds: 4, beating buy & hold: 3
- Excess return per fold: mean 47.78 pp, median 21.32 pp

## Robustness

| Period | Combos | Beat B&H | Profitable | Median return | B&H |
| --- | ---: | ---: | ---: | ---: | ---: |
| in_sample | 34 | 100% | 34 | 837.02% | 392.32% |
| out_of_sample | 34 | 21% | 18 | 2.35% | 16.74% |

**In-sample choice** fast=10, slow=200: in-sample return 1,325.41% (Sharpe 1.17); out-of-sample return -10.48% (Sharpe 0.05), rank 26 of 34.

**Permutation test** (out-of-sample, 200 shuffles): actual -10.48%, shuffled median 12.90%, 5–95% range -38.34% … 111.20%, p-value **0.707**.

| Cost multiplier | Return | Sharpe | Trades |
| ---: | ---: | ---: | ---: |
| ×1 | -10.48% | 0.05 | 7 |
| ×2 | -12.34% | 0.03 | 7 |
| ×3 | -14.16% | 0.00 | 7 |

## Walk-forward optimisation (rolling, train 1000, test 250, embargo 5)
- Folds: 8, profitable: 5, beating buy & hold: 3
- Chained out-of-sample return: 348.29% vs buy & hold 548.67% on the same windows; with switch-off after poor folds: 105.38% (2 folds skipped)
- Mean Sharpe: train 1.38 vs test 0.51 (a large gap means overfitting)
- Parameter change rate 0.86, 7 distinct sets

_Paper research only. Past results do not predict future returns._
