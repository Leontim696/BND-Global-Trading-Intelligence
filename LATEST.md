Latest run: `runs/2026-10-30T155020Z_41080738256_PORTFOLIO-etf_1d_all` (source 4816a3f, job success)

# BND backtest summary

## Verdict
**Best out-of-sample: volatility_target** (Sharpe 0.95 vs 0.84 for the basket). But its timing is indistinguishable from shuffled timing (adjusted p 1.000): the result comes from diversification and leverage, not from choosing when to trade.

## Multi-market portfolio
- Markets: 23 (2 bond, 7 commodity, 2 crypto, 6 forex, 6 index)
- Out-of-sample from 2022-01-24T00:00:00+00:00
- Sizing volatility, portfolio volatility target 15.0%, max leverage 3.0x, financing 0.0%/yr, kill switch at 30.0% drawdown, shorts on

| # | Strategy | Return | CAGR | Sharpe | Max drawdown | Avg leverage | Fills | Financing | Kill switch | p-value (adjusted) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| 1 | volatility_target | 90.20% | 14.45% | 0.95 | 25.98% | 2.65x | 239 | 156.97 | – | 0.146 (1.000) |
| 2 | momentum | 47.33% | 8.47% | 0.64 | 23.61% | 2.78x | 1182 | 360.34 | – | 0.732 (1.000) |
| 3 | regime_switch | 9.12% | 1.85% | 0.20 | 25.75% | 2.68x | 4496 | 348.27 | – | 0.122 (1.000) |
| 4 | bollinger_reversion | -1.55% | -0.33% | 0.06 | 27.82% | 2.42x | 3879 | 270.28 | – | 0.024 (0.293) |
| 5 | ema_crossover | -2.71% | -0.58% | 0.03 | 28.13% | 2.77x | 1271 | 300.06 | – | 0.854 (1.000) |
| 6 | donchian_breakout | -4.40% | -0.94% | -0.06 | 30.38% | 0.58x | 454 | 82.95 | 2023-05-24 | 1.000 (1.000) |
| 7 | sma_crossover | -9.81% | -2.15% | -0.20 | 30.10% | 0.68x | 348 | 86.19 | 2023-05-24 | 0.976 (1.000) |
| 8 | keltner_breakout | -12.86% | -2.85% | -0.22 | 30.16% | 0.63x | 1082 | 96.29 | 2023-10-13 | 1.000 (1.000) |
| 9 | adx_trend | -14.23% | -3.17% | -0.26 | 30.67% | 0.56x | 881 | 121.73 | 2023-08-29 | 0.878 (1.000) |
| 10 | macd | -22.58% | -5.23% | -0.36 | 30.66% | 2.13x | 2260 | 225.83 | 2025-10-24 | 0.512 (1.000) |
| 11 | rsi_reversion | -26.32% | -6.21% | -0.37 | 30.37% | 1.34x | 1391 | 191.92 | 2025-04-08 | 0.024 (0.293) |
| 12 | stochastic_reversion | -26.87% | -6.36% | -0.51 | 30.59% | 1.11x | 2180 | 124.49 | 2024-04-15 | 0.171 (1.000) |
| – | equal-weight basket (long, 1x) | 48.80% | 8.70% | 0.84 | 17.10% | 0.95x | 49 | – | – | – |

**Largest daily moves (check for bad data):** ETHEREUM -42.3% on 2020-03-12 (35 days > 15%), BITCOIN -37.2% on 2020-03-12 (20 days > 15%), SILVER -28.5% on 2026-01-30 (2 days > 15%), CRUDE_OIL -25.3% on 2020-03-09 (5 days > 15%), NATURAL_GAS -24.9% on 2026-02-02 (7 days > 15%), COPPER -19.3% on 2025-07-30 (1 days > 15%)

_Paper research only. Past results do not predict future returns._
