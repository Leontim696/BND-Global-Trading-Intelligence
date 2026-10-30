# BND backtest summary

## Verdict
**Beat the basket out of sample:** 417.42% vs 154.78%, in 10 of 12 windows. Preliminary: one dataset, no significance test.

## Portfolio walk-forward (sma_crossover, train 1460 days, test 365 days)
- Windows: 12, profitable: 9, beating the basket: 10, with kill switch: 0
- Chained out-of-sample: 417.42% vs basket 154.78%
- Mean Sharpe: train 1.04, test 1.00, basket 0.78; parameter change rate 0.36

| Test window | Parameters | Return | Sharpe | Max drawdown | Basket return | Kill switch |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 2014-01-05 → 2015-01-05 | fast=40, slow=150 | 20.01% | 1.52 | 9.49% | -5.24% | – |
| 2015-01-05 → 2016-01-05 | fast=40, slow=75 | -16.33% | -0.97 | 20.25% | -6.78% | – |
| 2016-01-05 → 2017-01-04 | fast=40, slow=50 | 36.38% | 2.01 | 6.95% | 9.84% | – |
| 2017-01-04 → 2018-01-04 | fast=40, slow=50 | 42.38% | 2.71 | 6.31% | 30.17% | – |
| 2018-01-04 → 2019-01-04 | fast=40, slow=50 | -14.35% | -0.79 | 25.51% | -15.22% | – |
| 2019-01-04 → 2020-01-04 | fast=40, slow=50 | 21.26% | 1.44 | 8.82% | 13.09% | – |
| 2020-01-04 → 2021-01-03 | fast=40, slow=50 | 36.40% | 1.88 | 16.76% | 25.55% | – |
| 2021-01-03 → 2022-01-03 | fast=20, slow=50 | 24.49% | 1.33 | 11.80% | 22.64% | – |
| 2022-01-03 → 2023-01-03 | fast=20, slow=50 | -5.64% | -0.24 | 15.46% | -8.09% | – |
| 2023-01-03 → 2024-01-03 | fast=20, slow=50 | 16.10% | 1.06 | 14.03% | 13.09% | – |
| 2024-01-03 → 2025-01-02 | fast=20, slow=50 | 20.28% | 1.23 | 13.93% | 13.32% | – |
| 2025-01-02 → 2026-01-02 | fast=40, slow=150 | 14.18% | 0.80 | 19.64% | 16.02% | – |

_Paper research only. Past results do not predict future returns._
