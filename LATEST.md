Latest run: `runs/2026-10-30T183830Z_41108221941_PORTFOLIO-etf-wfo_1d_regime_switch` (source e891e03, job success)

# BND backtest summary

## Verdict
**No evidence of an edge:** re-optimised every window, the strategy made 63.34% out of sample vs 154.78% for the basket, and beat it in 6 of 12 windows.

## Portfolio walk-forward (regime_switch, train 1460 days, test 365 days)
- Windows: 12, profitable: 8, beating the basket: 6, with kill switch: 0
- Chained out-of-sample: 63.34% vs basket 154.78%
- Mean Sharpe: train 0.78, test 0.35, basket 0.78; parameter change rate 0.27

| Test window | Parameters | Return | Sharpe | Max drawdown | Basket return | Kill switch |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 2014-01-05 → 2015-01-05 | window=20, trend_level=0.5 | 8.26% | 0.77 | 6.74% | -5.24% | – |
| 2015-01-05 → 2016-01-05 | window=20, trend_level=0.5 | -3.26% | -0.14 | 16.55% | -6.78% | – |
| 2016-01-05 → 2017-01-04 | window=40, trend_level=0.3 | 10.51% | 0.75 | 14.33% | 9.84% | – |
| 2017-01-04 → 2018-01-04 | window=40, trend_level=0.4 | -2.92% | -0.22 | 12.31% | 30.17% | – |
| 2018-01-04 → 2019-01-04 | window=40, trend_level=0.4 | -7.72% | -0.49 | 15.50% | -15.22% | – |
| 2019-01-04 → 2020-01-04 | window=20, trend_level=0.3 | 0.66% | 0.12 | 9.64% | 13.09% | – |
| 2020-01-04 → 2021-01-03 | window=20, trend_level=0.3 | 10.02% | 0.67 | 19.46% | 25.55% | – |
| 2021-01-03 → 2022-01-03 | window=20, trend_level=0.3 | 5.22% | 0.47 | 9.35% | 22.64% | – |
| 2022-01-03 → 2023-01-03 | window=20, trend_level=0.3 | 18.98% | 1.15 | 16.33% | -8.09% | – |
| 2023-01-03 → 2024-01-03 | window=20, trend_level=0.3 | 15.77% | 1.21 | 11.89% | 13.09% | – |
| 2024-01-03 → 2025-01-02 | window=20, trend_level=0.3 | -6.77% | -0.57 | 19.80% | 13.32% | – |
| 2025-01-02 → 2026-01-02 | window=20, trend_level=0.3 | 5.28% | 0.46 | 14.32% | 16.02% | – |

_Paper research only. Past results do not predict future returns._
