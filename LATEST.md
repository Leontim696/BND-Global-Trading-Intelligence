Latest run: `runs/2026-10-30T190205Z_41109868503_PORTFOLIO-etf-wfo_1d_sma_crossover` (source 77cc6f2, job success)

# BND backtest summary

## Verdict
**No evidence of an edge:** re-optimised every window, the strategy made 126.47% out of sample vs 154.78% for the basket, and beat it in 5 of 12 windows.

## Portfolio walk-forward (sma_crossover, train 1460 days, test 365 days)
- Windows: 12, profitable: 8, beating the basket: 5, with kill switch: 0
- Chained out-of-sample: 126.47% vs basket 154.78%
- Mean Sharpe: train 1.00, test 0.61, basket 0.78; parameter change rate 0.45

| Test window | Parameters | Return | Sharpe | Max drawdown | Basket return | Kill switch |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 2014-01-05 → 2015-01-05 | fast=50, slow=150 | 14.70% | 1.37 | 8.83% | -5.24% | – |
| 2015-01-05 → 2016-01-05 | fast=20, slow=75 | -6.83% | -0.40 | 13.73% | -6.78% | – |
| 2016-01-05 → 2017-01-04 | fast=40, slow=50 | 21.65% | 1.40 | 10.48% | 9.84% | – |
| 2017-01-04 → 2018-01-04 | fast=40, slow=50 | 18.58% | 1.74 | 7.14% | 30.17% | – |
| 2018-01-04 → 2019-01-04 | fast=40, slow=50 | 3.78% | 0.35 | 11.73% | -15.22% | – |
| 2019-01-04 → 2020-01-04 | fast=40, slow=50 | 4.71% | 0.49 | 9.17% | 13.09% | – |
| 2020-01-04 → 2021-01-03 | fast=40, slow=50 | 39.81% | 2.15 | 8.23% | 25.55% | – |
| 2021-01-03 → 2022-01-03 | fast=40, slow=50 | 7.14% | 0.60 | 13.51% | 22.64% | – |
| 2022-01-03 → 2023-01-03 | fast=20, slow=50 | 6.09% | 0.44 | 16.07% | -8.09% | – |
| 2023-01-03 → 2024-01-03 | fast=20, slow=50 | -11.94% | -0.80 | 28.84% | 13.09% | – |
| 2024-01-03 → 2025-01-02 | fast=10, slow=150 | -1.89% | -0.06 | 13.10% | 13.32% | – |
| 2025-01-02 → 2026-01-02 | fast=40, slow=150 | -1.53% | -0.01 | 17.35% | 16.02% | – |

_Paper research only. Past results do not predict future returns._
