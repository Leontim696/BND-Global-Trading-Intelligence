Latest run: `runs/2026-10-30T200113Z_41117939992_PORTFOLIO-etf-wfo_1d_sma_crossover` (source 6d76a8e, job success)

# BND backtest summary

## Verdict
**No evidence of an edge:** re-optimised every window, the strategy made 86.96% out of sample vs 154.78% for the basket, and beat it in 4 of 12 windows.

## Portfolio walk-forward (sma_crossover, train 1460 days, test 365 days)
- Windows: 12, profitable: 9, beating the basket: 4, with kill switch: 0
- Chained out-of-sample: 86.96% vs basket 154.78%
- Mean Sharpe: train 1.09, test 0.90, basket 0.78; parameter change rate 0.55

| Test window | Parameters | Return | Sharpe | Max drawdown | Basket return | Kill switch |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 2014-01-05 → 2015-01-05 | fast=50, slow=150 | 6.19% | 1.49 | 3.09% | -5.24% | – |
| 2015-01-05 → 2016-01-05 | fast=40, slow=50 | -4.79% | -0.67 | 7.68% | -6.78% | – |
| 2016-01-05 → 2017-01-04 | fast=40, slow=50 | 14.61% | 2.17 | 2.69% | 9.84% | – |
| 2017-01-04 → 2018-01-04 | fast=40, slow=50 | 14.73% | 2.80 | 2.53% | 30.17% | – |
| 2018-01-04 → 2019-01-04 | fast=40, slow=50 | -4.50% | -0.59 | 7.95% | -15.22% | – |
| 2019-01-04 → 2020-01-04 | fast=30, slow=175 | 8.58% | 1.51 | 3.09% | 13.09% | – |
| 2020-01-04 → 2021-01-03 | fast=40, slow=50 | 24.97% | 2.57 | 7.18% | 25.55% | – |
| 2021-01-03 → 2022-01-03 | fast=40, slow=50 | 9.29% | 1.11 | 6.33% | 22.64% | – |
| 2022-01-03 → 2023-01-03 | fast=40, slow=50 | -15.20% | -1.54 | 19.23% | -8.09% | – |
| 2023-01-03 → 2024-01-03 | fast=30, slow=125 | 1.18% | 0.20 | 7.02% | 13.09% | – |
| 2024-01-03 → 2025-01-02 | fast=10, slow=125 | 6.10% | 0.89 | 5.53% | 13.32% | – |
| 2025-01-02 → 2026-01-02 | fast=40, slow=150 | 9.07% | 0.92 | 10.21% | 16.02% | – |

_Paper research only. Past results do not predict future returns._
