# BND backtest summary

## Dataset
- File: `backtest-reports/BTCUSDT-4h.csv` (17152 candles, 4 gaps)
- Range: 2019-01-01T00:00:00+00:00 → 2026-10-30T08:00:00+00:00
- SHA-256: `5e094c7ec53092a0b91904e9904213c85c5469b2ac662b6235d375fb9748246d`

## Verdict
**No evidence of an edge.** Failed: permutation p-value < 0.05. Treat any profit above as luck or overfitting.

## Backtest: `sma_crossover`

**full** (2019-01-01T00:00:00+00:00 → 2026-10-30T08:00:00+00:00, risk gate: enforced)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Return | 47.10% | 1,989.48% |
| CAGR | 5.05% | 47.46% |
| Max drawdown | 20.98% | 77.04% |
| Sharpe | 0.63 | 0.95 |
| Trades | 198 | 1 |
| Time in market | 46.78% | 99.99% |
| Avg capital exposure | 9.92% | 99.99% |
| Entries vetoed by risk engine | 0 | 0 |

**in_sample** (2019-01-01T00:00:00+00:00 → 2024-06-24T16:00:00+00:00, risk gate: enforced)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Return | 45.39% | 1,501.41% |
| CAGR | 7.07% | 65.91% |
| Max drawdown | 20.98% | 77.04% |
| Sharpe | 0.79 | 1.11 |
| Trades | 138 | 1 |
| Time in market | 45.36% | 99.99% |
| Avg capital exposure | 9.73% | 99.99% |
| Entries vetoed by risk engine | 0 | 0 |

**out_of_sample** (2024-06-24T20:00:00+00:00 → 2026-10-30T08:00:00+00:00, risk gate: enforced)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Return | 1.18% | 30.09% |
| CAGR | 0.50% | 11.85% |
| Max drawdown | 8.09% | 53.45% |
| Sharpe | 0.11 | 0.47 |
| Trades | 60 | 1 |
| Time in market | 50.10% | 100.00% |
| Avg capital exposure | 10.37% | 100.00% |
| Entries vetoed by risk engine | 0 | 0 |

## Walk-forward (SMA long/flat, independent folds)
- Folds: 32, beating buy & hold: 11
- Excess return per fold: mean -8.45 pp, median -5.98 pp

## Robustness

| Period | Combos | Beat B&H | Profitable | Median return | B&H |
| --- | ---: | ---: | ---: | ---: | ---: |
| in_sample | 34 | 0% | 34 | 104.47% | 1,501.41% |
| out_of_sample | 34 | 0% | 30 | 6.25% | 30.09% |

**In-sample choice** fast=30, slow=175: in-sample return 172.46% (Sharpe 1.55); out-of-sample return 5.95% (Sharpe 0.44), rank 19 of 34.

**Permutation test** (out-of-sample, 200 shuffles): actual 5.95%, shuffled median 1.16%, 5–95% range -8.41% … 12.06%, p-value **0.244**.

| Cost multiplier | Return | Sharpe | Trades |
| ---: | ---: | ---: | ---: |
| ×1 | 5.95% | 0.44 | 21 |
| ×2 | 4.52% | 0.34 | 21 |
| ×3 | 3.31% | 0.26 | 21 |

_Paper research only. Past results do not predict future returns._
