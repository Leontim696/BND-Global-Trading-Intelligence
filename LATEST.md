Latest run: `runs/2026-10-30T194441Z_41117500553_PORTFOLIO-etf-wfo_1d_buy_and_hold` (source 6d76a8e, job success)

# BND backtest summary

## Verdict
**No evidence of an edge:** re-optimised every window, the strategy made 68.63% out of sample vs 154.78% for the basket, and beat it in 8 of 12 windows.

## Portfolio walk-forward (buy_and_hold, train 1460 days, test 365 days)
- Windows: 12, profitable: 7, beating the basket: 8, with kill switch: 1
- Chained out-of-sample: 68.63% vs basket 154.78%
- Mean Sharpe: train 0.16, test 0.56, basket 0.78; parameter change rate 0.00

| Test window | Parameters | Return | Sharpe | Max drawdown | Basket return | Kill switch |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 2014-01-05 → 2015-01-05 |  | -2.19% | -0.16 | 14.63% | -5.24% | – |
| 2015-01-05 → 2016-01-05 |  | -16.26% | -1.09 | 18.76% | -6.78% | – |
| 2016-01-05 → 2017-01-04 |  | 15.22% | 1.00 | 7.87% | 9.84% | – |
| 2017-01-04 → 2018-01-04 |  | 41.75% | 3.76 | 4.31% | 30.17% | – |
| 2018-01-04 → 2019-01-04 |  | -21.50% | -1.54 | 26.71% | -15.22% | – |
| 2019-01-04 → 2020-01-04 |  | 22.57% | 2.12 | 5.91% | 13.09% | – |
| 2020-01-04 → 2021-01-03 |  | -29.92% | -2.10 | 31.47% | 25.55% | 2020-03-18 |
| 2021-01-03 → 2022-01-03 |  | 24.76% | 1.49 | 8.07% | 22.64% | – |
| 2022-01-03 → 2023-01-03 |  | -16.89% | -0.88 | 25.73% | -8.09% | – |
| 2023-01-03 → 2024-01-03 |  | 13.86% | 1.09 | 11.35% | 13.09% | – |
| 2024-01-03 → 2025-01-02 |  | 28.05% | 1.63 | 12.61% | 13.32% | – |
| 2025-01-02 → 2026-01-02 |  | 23.67% | 1.35 | 17.76% | 16.02% | – |

_Paper research only. Past results do not predict future returns._
