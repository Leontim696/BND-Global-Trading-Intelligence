# BND backtest summary

## Verdict
**No evidence of an edge:** re-optimised every window, the strategy made 124.51% out of sample vs 154.78% for the basket, and beat it in 6 of 12 windows.

## Portfolio walk-forward (sma_crossover, train 1460 days, test 365 days)
- Windows: 12, profitable: 9, beating the basket: 6, with kill switch: 1
- Chained out-of-sample: 124.51% vs basket 154.78%
- Mean Sharpe: train 0.72, test 0.57, basket 0.78; parameter change rate 0.45

| Test window | Parameters | Return | Sharpe | Max drawdown | Basket return | Kill switch |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 2014-01-05 → 2015-01-05 | fast=40; slow=150 | 12.95% | 1.03 | 11.18% | -5.24% | – |
| 2015-01-05 → 2016-01-05 | fast=40; slow=75 | -20.35% | -1.26 | 22.86% | -6.78% | – |
| 2016-01-05 → 2017-01-04 | fast=40; slow=50 | 30.58% | 1.74 | 7.22% | 9.84% | – |
| 2017-01-04 → 2018-01-04 | fast=40; slow=50 | 34.40% | 2.27 | 6.44% | 30.17% | – |
| 2018-01-04 → 2019-01-04 | fast=40; slow=50 | -18.83% | -1.09 | 28.55% | -15.22% | – |
| 2019-01-04 → 2020-01-04 | fast=40; slow=50 | 15.19% | 1.08 | 9.52% | 13.09% | – |
| 2020-01-04 → 2021-01-03 | fast=40; slow=50 | 32.26% | 1.70 | 17.59% | 25.55% | – |
| 2021-01-03 → 2022-01-03 | fast=40; slow=50 | 16.26% | 0.93 | 12.43% | 22.64% | – |
| 2022-01-03 → 2023-01-03 | fast=40; slow=50 | -23.24% | -1.31 | 30.19% | -8.09% | 2022-11-28 |
| 2023-01-03 → 2024-01-03 | fast=10; slow=150 | 2.60% | 0.24 | 12.30% | 13.09% | – |
| 2024-01-03 → 2025-01-02 | fast=20; slow=50 | 14.65% | 0.93 | 14.88% | 13.32% | – |
| 2025-01-02 → 2026-01-02 | fast=40; slow=150 | 9.54% | 0.58 | 20.18% | 16.02% | – |

_Paper research only. Past results do not predict future returns._
