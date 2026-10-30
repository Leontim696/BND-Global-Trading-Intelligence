Latest run: `runs/2026-10-30T125655Z_41058895982_BTCUSDT_4h_volatility_target` (source ec4bb0e, job success)

# BND backtest summary

## Dataset
- File: `backtest-reports/BTCUSDT-4h.csv` (17152 candles, 4 gaps)
- Range: 2019-01-01T00:00:00+00:00 → 2026-10-30T08:00:00+00:00
- SHA-256: `5e094c7ec53092a0b91904e9904213c85c5469b2ac662b6235d375fb9748246d`

## Verdict
**No evidence of an edge.** Failed: permutation p-value < 0.05. Treat any profit above as luck or overfitting.

Out-of-sample, risk-adjusted: Sharpe 0.52 vs 0.47 for buy & hold; max drawdown 31.16% vs 53.45%; return 28.32% vs 30.09% with 48.21% average capital invested.

## Backtest: `volatility_target`

**full** (2019-01-01T00:00:00+00:00 → 2026-10-30T08:00:00+00:00, risk gate: disabled_research_only)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Return | 338.39% | 1,989.48% |
| CAGR | 20.78% | 47.46% |
| Max drawdown | 42.36% | 77.04% |
| Sharpe | 0.79 | 0.95 |
| Trades | 58 | 1 |
| Time in market | 54.34% | 99.99% |
| Avg capital exposure | 43.40% | 99.99% |
| Entries vetoed by risk engine | 0 | 0 |

**in_sample** (2019-01-01T00:00:00+00:00 → 2024-06-24T16:00:00+00:00, risk gate: disabled_research_only)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Return | 240.61% | 1,501.41% |
| CAGR | 25.07% | 65.91% |
| Max drawdown | 42.36% | 77.04% |
| Sharpe | 0.89 | 1.11 |
| Trades | 35 | 1 |
| Time in market | 54.81% | 99.99% |
| Avg capital exposure | 41.34% | 99.99% |
| Entries vetoed by risk engine | 0 | 0 |

**out_of_sample** (2024-06-24T20:00:00+00:00 → 2026-10-30T08:00:00+00:00, risk gate: disabled_research_only)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Return | 28.32% | 30.09% |
| CAGR | 11.20% | 11.85% |
| Max drawdown | 31.16% | 53.45% |
| Sharpe | 0.52 | 0.47 |
| Trades | 24 | 1 |
| Time in market | 53.26% | 100.00% |
| Avg capital exposure | 48.21% | 100.00% |
| Entries vetoed by risk engine | 0 | 0 |

## Walk-forward (SMA long/flat, independent folds)
- Folds: 32, beating buy & hold: 11
- Excess return per fold: mean -8.45 pp, median -5.98 pp

## Robustness

| Period | Combos | Beat B&H | Profitable | Median return | B&H |
| --- | ---: | ---: | ---: | ---: | ---: |
| in_sample | 42 | 0% | 42 | 284.37% | 1,501.41% |
| out_of_sample | 42 | 7% | 42 | 23.55% | 30.09% |

**In-sample choice** target_vol=20, lookback=240: in-sample return 146.77% (Sharpe 1.09); out-of-sample return 20.57% (Sharpe 0.59), rank 2 of 42.

**Permutation test** (out-of-sample, 200 shuffles): actual 20.57%, shuffled median 4.99%, 5–95% range -16.51% … 43.62%, p-value **0.244**.

| Cost multiplier | Return | Sharpe | Trades |
| ---: | ---: | ---: | ---: |
| ×1 | 20.57% | 0.59 | 24 |
| ×2 | 16.36% | 0.50 | 24 |
| ×3 | 12.30% | 0.40 | 24 |

_Paper research only. Past results do not predict future returns._
