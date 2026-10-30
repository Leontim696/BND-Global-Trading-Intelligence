Latest run: `runs/2026-10-30T184243Z_41108867617_PORTFOLIO-etf-wfo_1d_cross_momentum` (source e891e03, job success)

# BND backtest summary

## Verdict
**No evidence of an edge:** re-optimised every window, the strategy made 95.45% out of sample vs 154.78% for the basket, and beat it in 5 of 12 windows.

## Portfolio walk-forward (cross_momentum, train 1460 days, test 365 days)
- Windows: 12, profitable: 8, beating the basket: 5, with kill switch: 0
- Chained out-of-sample: 95.45% vs basket 154.78%
- Mean Sharpe: train 0.93, test 0.44, basket 0.78; parameter change rate 0.45

| Test window | Parameters | Return | Sharpe | Max drawdown | Basket return | Kill switch |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 2014-01-05 → 2015-01-05 | lookback=126, skip=21 | 17.75% | 1.32 | 12.09% | -5.24% | – |
| 2015-01-05 → 2016-01-05 | lookback=252, skip=0 | 18.30% | 1.10 | 11.16% | -6.78% | – |
| 2016-01-05 → 2017-01-04 | lookback=252, skip=0 | -24.74% | -1.60 | 29.41% | 9.84% | – |
| 2017-01-04 → 2018-01-04 | lookback=189, skip=21 | 27.31% | 1.82 | 7.08% | 30.17% | – |
| 2018-01-04 → 2019-01-04 | lookback=189, skip=21 | -3.57% | -0.16 | 13.47% | -15.22% | – |
| 2019-01-04 → 2020-01-04 | lookback=189, skip=0 | -7.62% | -0.52 | 14.14% | 13.09% | – |
| 2020-01-04 → 2021-01-03 | lookback=189, skip=21 | 33.76% | 1.82 | 8.18% | 25.55% | – |
| 2021-01-03 → 2022-01-03 | lookback=189, skip=21 | 9.54% | 0.63 | 14.37% | 22.64% | – |
| 2022-01-03 → 2023-01-03 | lookback=189, skip=21 | 24.43% | 1.51 | 11.95% | -8.09% | – |
| 2023-01-03 → 2024-01-03 | lookback=189, skip=21 | -24.19% | -1.93 | 25.59% | 13.09% | – |
| 2024-01-03 → 2025-01-02 | lookback=252, skip=21 | 3.68% | 0.33 | 14.33% | 13.32% | – |
| 2025-01-02 → 2026-01-02 | lookback=252, skip=21 | 14.70% | 0.93 | 11.46% | 16.02% | – |

_Paper research only. Past results do not predict future returns._
