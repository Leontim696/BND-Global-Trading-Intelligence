# BND backtest summary

## Verdict
**No evidence of an edge:** no strategy beat the simple equal-weight basket on out-of-sample Sharpe.

## Multi-market portfolio
- Markets: 23 (2 bond, 7 commodity, 2 crypto, 6 forex, 6 index)
- Out-of-sample from 2022-01-26T00:00:00+00:00
- Sizing volatility, portfolio volatility target 15.0%, max leverage 3.0x, financing 5.0%/yr, kill switch at 30.0% drawdown, shorts on

| # | Strategy | Return | CAGR | Sharpe | Max drawdown | Avg leverage | Fills | Financing | Kill switch | p-value (adjusted) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| 1 | volatility_target | 18.46% | 3.62% | 0.30 | 28.96% | 2.69x | 238 | 4,157.79 | – | 0.342 (1.000) |
| 2 | cross_momentum | -5.10% | -1.09% | -0.03 | 30.64% | 1.74x | 1488 | 3,187.26 | 2025-03-10 | 0.927 (1.000) |
| 3 | donchian_breakout | -8.54% | -1.86% | -0.16 | 30.53% | 0.51x | 422 | 743.93 | 2023-04-03 | 0.927 (1.000) |
| 4 | adx_trend | -13.63% | -3.03% | -0.25 | 30.94% | 0.53x | 835 | 673.36 | 2023-08-02 | 0.488 (1.000) |
| 5 | keltner_breakout | -15.24% | -3.41% | -0.29 | 31.14% | 0.59x | 1002 | 719.11 | 2023-09-21 | 1.000 (1.000) |
| 6 | momentum | -13.98% | -3.11% | -0.30 | 30.28% | 0.95x | 446 | 1,471.21 | 2023-11-08 | 0.756 (1.000) |
| 7 | sma_crossover | -14.03% | -3.12% | -0.32 | 30.64% | 0.61x | 329 | 960.26 | 2023-04-14 | 0.195 (1.000) |
| 8 | regime_switch | -21.32% | -4.91% | -0.41 | 30.40% | 1.72x | 2965 | 2,428.23 | 2025-03-10 | 0.098 (0.878) |
| 9 | ema_crossover | -20.02% | -4.58% | -0.46 | 31.28% | 0.80x | 489 | 1,223.80 | 2023-08-02 | 0.317 (1.000) |
| 10 | rsi_reversion | -26.92% | -6.37% | -0.48 | 30.40% | 0.84x | 912 | 968.57 | 2024-04-15 | 0.024 (0.317) |
| 11 | macd | -28.38% | -6.77% | -0.55 | 30.57% | 1.80x | 1880 | 2,516.32 | 2025-04-03 | 0.073 (0.732) |
| 12 | stochastic_reversion | -25.98% | -6.12% | -0.62 | 30.02% | 0.53x | 1165 | 634.74 | 2023-04-13 | 0.049 (0.537) |
| 13 | bollinger_reversion | -25.30% | -5.94% | -0.65 | 30.22% | 0.39x | 735 | 415.60 | 2023-01-29 | 0.024 (0.317) |
| – | equal-weight basket (long, 1x) | 45.63% | 8.21% | 0.79 | 16.96% | 0.95x | 49 | – | – | – |

**In EUR, unhedged** (a EUR investor; dollar moves included):

| Strategy | Return | CAGR | Sharpe | Max drawdown |
| --- | ---: | ---: | ---: | ---: |
| volatility_target | 19.75% | 3.86% | 0.32 | 22.25% |
| cross_momentum | -4.07% | -0.87% | 0.02 | 43.39% |
| donchian_breakout | -7.55% | -1.63% | -0.06 | 41.96% |
| adx_trend | -12.69% | -2.81% | -0.15 | 42.39% |
| keltner_breakout | -14.32% | -3.19% | -0.17 | 41.73% |
| momentum | -13.05% | -2.89% | -0.16 | 43.82% |
| sma_crossover | -13.09% | -2.90% | -0.16 | 42.14% |
| regime_switch | -20.46% | -4.69% | -0.27 | 37.17% |
| ema_crossover | -19.15% | -4.36% | -0.28 | 42.85% |
| rsi_reversion | -26.12% | -6.16% | -0.40 | 34.38% |
| macd | -27.60% | -6.55% | -0.42 | 43.42% |
| stochastic_reversion | -25.17% | -5.91% | -0.46 | 34.11% |
| bollinger_reversion | -24.48% | -5.72% | -0.48 | 34.23% |
| equal-weight basket | 47.21% | 8.46% | 0.73 | 14.59% |

**Largest daily moves (check for bad data):** ETHEREUM -42.3% on 2020-03-12 (35 days > 15%), BITCOIN -37.2% on 2020-03-12 (20 days > 15%), SILVER -28.5% on 2026-01-30 (2 days > 15%), CRUDE_OIL -25.3% on 2020-03-09 (5 days > 15%), NATURAL_GAS -24.9% on 2026-02-02 (7 days > 15%), COPPER -19.3% on 2025-07-30 (1 days > 15%)

_Paper research only. Past results do not predict future returns._
