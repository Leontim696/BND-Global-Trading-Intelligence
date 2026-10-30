# BND backtest summary

## Dataset
- File: `backtest-reports/BTCUSDT-4h.csv` (17152 candles, 4 gaps)
- Range: 2019-01-01T00:00:00+00:00 → 2026-10-30T08:00:00+00:00
- SHA-256: `5e094c7ec53092a0b91904e9904213c85c5469b2ac662b6235d375fb9748246d`

## Verdict
**No evidence of an edge.** Failed: still positive at 2× costs. Treat any profit above as luck or overfitting.

Out-of-sample, risk-adjusted: Sharpe 0.16 vs 0.47 for buy & hold; max drawdown 44.75% vs 53.45%; return -3.06% vs 30.09% with 91.17% average capital invested.

## Backtest: `volatility_target`
Costs per fill: fee 0.1%, slippage 0.05%; funding 10.0%/yr on open positions; cash interest 4.0%/yr; shorts allowed.

**full** (2019-01-01T00:00:00+00:00 → 2026-10-30T08:00:00+00:00, risk gate: disabled_research_only)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Return | 58.94% | 1,989.52% |
| CAGR | 6.10% | 47.46% |
| Max drawdown | 64.41% | 77.04% |
| Sharpe | 0.35 | 0.95 |
| Trades | 115 | 1 |
| Time in market | 92.99% | 99.99% |
| Avg capital exposure | 72.76% | 99.99% |
| Funding paid | 6,577.45 | 0.00 |
| Interest earned | 935.05 | 0.18 |
| Entries vetoed by risk engine | 0 | 0 |

**in_sample** (2019-01-01T00:00:00+00:00 → 2024-06-24T16:00:00+00:00, risk gate: disabled_research_only)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Return | 63.48% | 1,501.44% |
| CAGR | 9.39% | 65.91% |
| Max drawdown | 64.41% | 77.04% |
| Sharpe | 0.43 | 1.11 |
| Trades | 69 | 1 |
| Time in market | 89.99% | 99.99% |
| Avg capital exposure | 64.88% | 99.99% |
| Funding paid | 3,422.08 | 0.00 |
| Interest earned | 759.07 | 0.18 |
| Entries vetoed by risk engine | 0 | 0 |

**out_of_sample** (2024-06-24T20:00:00+00:00 → 2026-10-30T08:00:00+00:00, risk gate: disabled_research_only)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Return | -3.06% | 30.09% |
| CAGR | -1.31% | 11.85% |
| Max drawdown | 44.75% | 53.45% |
| Sharpe | 0.16 | 0.47 |
| Trades | 47 | 1 |
| Time in market | 100.00% | 100.00% |
| Avg capital exposure | 91.17% | 100.00% |
| Funding paid | 1,924.41 | 0.00 |
| Interest earned | 107.33 | 0.00 |
| Entries vetoed by risk engine | 0 | 0 |

## Walk-forward (SMA long/flat, independent folds)
- Folds: 32, beating buy & hold: 11
- Excess return per fold: mean -8.45 pp, median -5.98 pp

## Robustness

| Period | Combos | Beat B&H | Profitable | Median return | B&H |
| --- | ---: | ---: | ---: | ---: | ---: |
| in_sample | 42 | 0% | 40 | 49.64% | 1,501.44% |
| out_of_sample | 42 | 0% | 13 | -13.92% | 30.09% |

**In-sample choice** target_vol=20, lookback=240: in-sample return 89.34% (Sharpe 0.67); out-of-sample return 13.81% (Sharpe 0.37), rank 1 of 42.

**Permutation test** (out-of-sample, 200 shuffles): actual 13.81%, shuffled median -32.84%, 5–95% range -59.62% … 11.49%, p-value **0.045**.

| Cost multiplier | Return | Sharpe | Trades |
| ---: | ---: | ---: | ---: |
| ×1 | 13.81% | 0.37 | 47 |
| ×2 | -5.11% | -0.01 | 47 |
| ×3 | -20.90% | -0.38 | 47 |

_Paper research only. Past results do not predict future returns._
