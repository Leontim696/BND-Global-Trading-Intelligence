Latest run: `runs/2026-10-30T213102Z_41130102691_PORTFOLIO-etf-wfo_1d_buy_and_hold` (source 0d7d4d6, job success)

# BND backtest summary

## Verdict
**No evidence of an edge:** re-optimised every window, the strategy made 69.28% out of sample vs 154.78% for the basket, and beat it in 4 of 12 windows.

## Portfolio walk-forward (buy_and_hold, train 1460 days, test 365 days)
- Windows: 12, profitable: 8, beating the basket: 4, with kill switch: 0
- Chained out-of-sample: 69.28% vs basket 154.78%
- Mean Sharpe: train 0.58, test 0.90, basket 0.78; parameter change rate 0.00

| Test window | Parameters | Return | Sharpe | Max drawdown | Basket return | Kill switch |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 2014-01-05 → 2015-01-05 |  | -0.24% | -0.05 | 5.11% | -5.24% | – |
| 2015-01-05 → 2016-01-05 |  | -4.96% | -0.96 | 6.58% | -6.78% | – |
| 2016-01-05 → 2017-01-04 |  | 3.10% | 0.62 | 2.79% | 9.84% | – |
| 2017-01-04 → 2018-01-04 |  | 15.18% | 3.84 | 1.92% | 30.17% | – |
| 2018-01-04 → 2019-01-04 |  | -7.53% | -1.32 | 9.93% | -15.22% | – |
| 2019-01-04 → 2020-01-04 |  | 7.60% | 2.23 | 1.75% | 13.09% | – |
| 2020-01-04 → 2021-01-03 |  | 10.96% | 1.15 | 12.57% | 25.55% | – |
| 2021-01-03 → 2022-01-03 |  | 8.51% | 1.32 | 3.48% | 22.64% | – |
| 2022-01-03 → 2023-01-03 |  | -5.55% | -0.76 | 10.28% | -8.09% | – |
| 2023-01-03 → 2024-01-03 |  | 7.15% | 1.30 | 4.10% | 13.09% | – |
| 2024-01-03 → 2025-01-02 |  | 9.75% | 1.57 | 4.97% | 13.32% | – |
| 2025-01-02 → 2026-01-02 |  | 13.00% | 1.85 | 6.36% | 16.02% | – |

_Paper research only. Past results do not predict future returns._
