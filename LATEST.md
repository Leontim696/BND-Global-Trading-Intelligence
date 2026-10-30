Latest run: `runs/2026-10-30T214311Z_41131751749_PORTFOLIO-etf-wfo_1d_sma_crossover` (source 500a496, job success)

# BND backtest summary

## Verdict
**No evidence of an edge:** re-optimised every window, the strategy made 145.93% out of sample vs 154.78% for the basket, and beat it in 4 of 12 windows.

## Portfolio walk-forward (sma_crossover, train 1460 days, test 365 days)
- Windows: 12, profitable: 8, beating the basket: 4, with kill switch: 0
- Chained out-of-sample: 145.93% vs basket 154.78%
- Mean Sharpe: train 0.81, test 0.73, basket 0.78; parameter change rate 0.55

| Test window | Parameters | Return | Sharpe | Max drawdown | Basket return | Kill switch |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 2014-01-05 → 2015-01-05 | fast=40; slow=150 | 9.88% | 1.18 | 6.86% | -5.24% | – |
| 2015-01-05 → 2016-01-05 | fast=40; slow=75 | -13.56% | -1.04 | 16.31% | -6.78% | – |
| 2016-01-05 → 2017-01-04 | fast=40; slow=50 | 23.76% | 1.80 | 5.03% | 9.84% | – |
| 2017-01-04 → 2018-01-04 | fast=40; slow=50 | 24.36% | 2.38 | 4.69% | 30.17% | – |
| 2018-01-04 → 2019-01-04 | fast=40; slow=50 | -12.61% | -0.94 | 19.20% | -15.22% | – |
| 2019-01-04 → 2020-01-04 | fast=40; slow=50 | 12.10% | 1.18 | 6.13% | 13.09% | – |
| 2020-01-04 → 2021-01-03 | fast=40; slow=50 | 39.44% | 2.36 | 12.21% | 25.55% | – |
| 2021-01-03 → 2022-01-03 | fast=40; slow=50 | 13.87% | 0.92 | 11.79% | 22.64% | – |
| 2022-01-03 → 2023-01-03 | fast=20; slow=50 | -10.33% | -0.60 | 17.70% | -8.09% | – |
| 2023-01-03 → 2024-01-03 | fast=30; slow=150 | -0.62% | 0.01 | 13.72% | 13.09% | – |
| 2024-01-03 → 2025-01-02 | fast=20; slow=150 | 11.90% | 0.91 | 11.01% | 13.32% | – |
| 2025-01-02 → 2026-01-02 | fast=40; slow=150 | 8.45% | 0.57 | 18.49% | 16.02% | – |

_Paper research only. Past results do not predict future returns._
