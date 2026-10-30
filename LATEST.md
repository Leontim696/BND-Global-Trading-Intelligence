Latest run: `runs/2026-10-30T213001Z_41130064919_PORTFOLIO-etf-wfo_1d_sma_crossover` (source 0d7d4d6, job success)

# BND backtest summary

## Verdict
**No evidence of an edge:** re-optimised every window, the strategy made 80.30% out of sample vs 154.78% for the basket, and beat it in 4 of 12 windows.

## Portfolio walk-forward (sma_crossover, train 1460 days, test 365 days)
- Windows: 12, profitable: 9, beating the basket: 4, with kill switch: 0
- Chained out-of-sample: 80.30% vs basket 154.78%
- Mean Sharpe: train 1.05, test 0.86, basket 0.78; parameter change rate 0.55

| Test window | Parameters | Return | Sharpe | Max drawdown | Basket return | Kill switch |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 2014-01-05 → 2015-01-05 | fast=50, slow=150 | 5.85% | 1.41 | 3.15% | -5.24% | – |
| 2015-01-05 → 2016-01-05 | fast=40, slow=50 | -4.97% | -0.70 | 7.86% | -6.78% | – |
| 2016-01-05 → 2017-01-04 | fast=40, slow=50 | 14.37% | 2.13 | 2.77% | 9.84% | – |
| 2017-01-04 → 2018-01-04 | fast=40, slow=50 | 14.26% | 2.71 | 2.56% | 30.17% | – |
| 2018-01-04 → 2019-01-04 | fast=40, slow=50 | -4.65% | -0.61 | 8.10% | -15.22% | – |
| 2019-01-04 → 2020-01-04 | fast=30, slow=175 | 8.16% | 1.44 | 3.08% | 13.09% | – |
| 2020-01-04 → 2021-01-03 | fast=40, slow=50 | 24.62% | 2.54 | 7.22% | 25.55% | – |
| 2021-01-03 → 2022-01-03 | fast=40, slow=50 | 9.04% | 1.08 | 6.37% | 22.64% | – |
| 2022-01-03 → 2023-01-03 | fast=40, slow=50 | -15.34% | -1.55 | 19.31% | -8.09% | – |
| 2023-01-03 → 2024-01-03 | fast=30, slow=125 | 0.88% | 0.16 | 7.03% | 13.09% | – |
| 2024-01-03 → 2025-01-02 | fast=10, slow=125 | 5.83% | 0.85 | 5.73% | 13.32% | – |
| 2025-01-02 → 2026-01-02 | fast=40, slow=150 | 8.31% | 0.85 | 10.33% | 16.02% | – |

_Paper research only. Past results do not predict future returns._
