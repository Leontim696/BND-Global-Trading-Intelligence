# BND backtest summary

## Verdict
**No evidence of an edge:** re-optimised every window, the strategy made 114.14% out of sample vs 154.78% for the basket, and beat it in 4 of 12 windows.

## Portfolio walk-forward (sma_crossover, train 1460 days, test 365 days)
- Windows: 12, profitable: 10, beating the basket: 4, with kill switch: 1
- Chained out-of-sample: 114.14% vs basket 154.78%
- Mean Sharpe: train 0.38, test 0.51, basket 0.78; parameter change rate 0.55

| Test window | Parameters | Return | Sharpe | Max drawdown | Basket return | Kill switch |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 2014-01-05 → 2015-01-05 | fast=40, slow=150 | 8.27% | 0.69 | 12.33% | -5.24% | – |
| 2015-01-05 → 2016-01-05 | fast=40, slow=75 | -22.91% | -1.46 | 25.03% | -6.78% | – |
| 2016-01-05 → 2017-01-04 | fast=40, slow=50 | 26.27% | 1.53 | 7.43% | 9.84% | – |
| 2017-01-04 → 2018-01-04 | fast=40, slow=50 | 29.23% | 1.97 | 6.55% | 30.17% | – |
| 2018-01-04 → 2019-01-04 | fast=40, slow=50 | -21.59% | -1.38 | 30.45% | -15.22% | 2018-11-13 |
| 2019-01-04 → 2020-01-04 | fast=40, slow=50 | 10.84% | 0.80 | 9.97% | 13.09% | – |
| 2020-01-04 → 2021-01-03 | fast=40, slow=50 | 31.47% | 1.66 | 18.24% | 25.55% | – |
| 2021-01-03 → 2022-01-03 | fast=10, slow=100 | 14.89% | 0.89 | 9.60% | 22.64% | – |
| 2022-01-03 → 2023-01-03 | fast=20, slow=150 | 5.39% | 0.39 | 14.17% | -8.09% | – |
| 2023-01-03 → 2024-01-03 | fast=10, slow=150 | 0.19% | 0.09 | 13.40% | 13.09% | – |
| 2024-01-03 → 2025-01-02 | fast=10, slow=150 | 6.01% | 0.44 | 14.05% | 13.32% | – |
| 2025-01-02 → 2026-01-02 | fast=40, slow=150 | 7.02% | 0.45 | 20.55% | 16.02% | – |

_Paper research only. Past results do not predict future returns._
