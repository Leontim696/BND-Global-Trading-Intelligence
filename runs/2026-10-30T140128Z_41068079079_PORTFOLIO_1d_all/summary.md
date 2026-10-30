# BND backtest summary

## Verdict
**No evidence of an edge:** no strategy beat the simple equal-weight basket on out-of-sample Sharpe.

## Multi-market portfolio
- Markets: 22 (1 bond, 8 commodity, 2 crypto, 6 forex, 5 index)
- Out-of-sample from 2022-01-23T00:00:00+00:00
- Sizing volatility, portfolio volatility target 15.0%, max leverage 3.0x, financing 5.0%/yr, kill switch at 30.0% drawdown, shorts on

| # | Strategy | Return | CAGR | Sharpe | Max drawdown | Avg leverage | Fills | Financing | Kill switch |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | volatility_target | 20.99% | 4.08% | 0.35 | 26.53% | 2.99x | 213 | 4,843.45 | – |
| 2 | donchian_breakout | -7.66% | -1.66% | -0.10 | 30.74% | 0.59x | 266 | 938.58 | 2023-03-10 |
| 3 | bollinger_reversion | -23.32% | -5.42% | -0.38 | 30.31% | 1.09x | 1148 | 1,331.14 | 2024-04-18 |
| 4 | macd | -22.52% | -5.21% | -0.40 | 30.09% | 1.81x | 1437 | 2,724.29 | 2024-12-13 |
| 5 | rsi_reversion | -25.96% | -6.11% | -0.41 | 31.15% | 1.33x | 809 | 1,238.23 | 2026-01-23 |
| 6 | momentum | -19.94% | -4.56% | -0.42 | 30.65% | 1.05x | 454 | 1,584.49 | 2023-09-28 |
| 7 | adx_trend | -18.58% | -4.22% | -0.42 | 30.23% | 0.51x | 483 | 488.31 | 2023-08-29 |
| 8 | sma_crossover | -20.20% | -4.62% | -0.42 | 31.32% | 0.73x | 238 | 1,162.26 | 2023-03-17 |
| 9 | ema_crossover | -22.77% | -5.28% | -0.45 | 30.20% | 0.94x | 387 | 1,412.58 | 2023-07-23 |
| 10 | keltner_breakout | -23.22% | -5.39% | -0.45 | 30.28% | 0.60x | 587 | 610.10 | 2023-10-10 |
| 11 | stochastic_reversion | -25.63% | -6.02% | -0.56 | 30.25% | 0.56x | 736 | 742.87 | 2023-01-13 |
| – | equal-weight basket (long, 1x) | 41.69% | 7.58% | 0.78 | 16.42% | 0.93x | 47 | – | – |

_Paper research only. Past results do not predict future returns._
