Latest run: `runs/2026-10-30T194334Z_41116003179_PORTFOLIO-etf-wfo_1d_buy_and_hold` (source 053c41f, job success)

# BND backtest summary

## Verdict
**No evidence of an edge:** re-optimised every window, the strategy made -34.60% out of sample vs 154.78% for the basket, and beat it in 1 of 12 windows.

## Portfolio walk-forward (buy_and_hold, train 1460 days, test 365 days)
- Windows: 12, profitable: 7, beating the basket: 1, with kill switch: 2
- Chained out-of-sample: -34.60% vs basket 154.78%
- Mean Sharpe: train -0.53, test -0.05, basket 0.78; parameter change rate 0.00

| Test window | Parameters | Return | Sharpe | Max drawdown | Basket return | Kill switch |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 2014-01-05 → 2015-01-05 |  | -13.06% | -1.25 | 20.66% | -5.24% | – |
| 2015-01-05 → 2016-01-05 |  | -22.66% | -1.62 | 22.87% | -6.78% | – |
| 2016-01-05 → 2017-01-04 |  | 4.48% | 0.36 | 10.17% | 9.84% | – |
| 2017-01-04 → 2018-01-04 |  | 29.56% | 2.78 | 4.94% | 30.17% | – |
| 2018-01-04 → 2019-01-04 |  | -26.55% | -2.00 | 30.36% | -15.22% | 2018-12-17 |
| 2019-01-04 → 2020-01-04 |  | 12.05% | 1.18 | 6.94% | 13.09% | – |
| 2020-01-04 → 2021-01-03 |  | -31.37% | -2.22 | 32.66% | 25.55% | 2020-03-18 |
| 2021-01-03 → 2022-01-03 |  | 13.72% | 0.91 | 9.48% | 22.64% | – |
| 2022-01-03 → 2023-01-03 |  | -20.50% | -1.13 | 27.78% | -8.09% | – |
| 2023-01-03 → 2024-01-03 |  | 6.36% | 0.54 | 12.81% | 13.09% | – |
| 2024-01-03 → 2025-01-02 |  | 16.40% | 1.01 | 13.81% | 13.32% | – |
| 2025-01-02 → 2026-01-02 |  | 13.65% | 0.85 | 18.19% | 16.02% | – |

_Paper research only. Past results do not predict future returns._
