Latest run: `runs/2026-10-30T140917Z_41069169912_PORTFOLIO_1d_all` (source e3b5485, job success)

# BND backtest summary

## Verdict
**Best out-of-sample: volatility_target** (Sharpe 1.01 vs 0.74 for the basket). Not yet proven: there is no permutation test for portfolios and several strategies were compared.

## Multi-market portfolio
- Markets: 22 (1 bond, 8 commodity, 2 crypto, 6 forex, 5 index)
- Out-of-sample from 2022-01-23T00:00:00+00:00
- Sizing volatility, portfolio volatility target 15.0%, max leverage 3.0x, financing 0.0%/yr, kill switch at 30.0% drawdown, shorts on

| # | Strategy | Return | CAGR | Sharpe | Max drawdown | Avg leverage | Fills | Financing | Kill switch |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | volatility_target | 80.67% | 13.21% | 1.01 | 21.34% | 2.85x | 237 | 188.49 | – |
| 2 | momentum | 36.78% | 6.79% | 0.57 | 19.97% | 2.89x | 1193 | 371.55 | – |
| 3 | ema_crossover | 3.35% | 0.69% | 0.12 | 24.43% | 2.84x | 1183 | 330.93 | – |
| 4 | keltner_breakout | -12.13% | -2.68% | -0.07 | 29.89% | 2.12x | 2745 | 274.49 | – |
| 5 | donchian_breakout | -7.82% | -1.69% | -0.12 | 30.75% | 0.70x | 453 | 106.61 | 2023-07-19 |
| 6 | adx_trend | -12.41% | -2.74% | -0.22 | 30.42% | 0.59x | 883 | 120.37 | 2023-07-24 |
| 7 | macd | -20.04% | -4.58% | -0.34 | 30.58% | 2.24x | 2101 | 264.62 | 2025-11-10 |
| 8 | sma_crossover | -17.16% | -3.87% | -0.41 | 30.43% | 0.76x | 343 | 91.48 | 2023-06-16 |
| 9 | bollinger_reversion | -26.28% | -6.20% | -0.47 | 32.21% | 1.26x | 1991 | 146.76 | 2024-08-05 |
| 10 | rsi_reversion | -30.24% | -7.28% | -0.55 | 31.88% | 0.94x | 939 | 143.04 | 2024-05-20 |
| 11 | stochastic_reversion | -27.27% | -6.46% | -0.67 | 31.71% | 0.67x | 1278 | 80.56 | 2023-06-15 |
| – | equal-weight basket (long, 1x) | 38.51% | 7.07% | 0.74 | 16.71% | 0.94x | 48 | – | – |

**Largest daily moves (check for bad data):** NATURAL_GAS -47.5% on 2026-01-29 (24 days > 15%), ETHEREUM -42.3% on 2020-03-12 (35 days > 15%), BITCOIN -37.2% on 2020-03-12 (20 days > 15%), SILVER -31.3% on 2026-01-30 (2 days > 15%), CRUDE_OIL 25.1% on 2020-04-30 (11 days > 15%), CORN -23.6% on 2013-07-15 (3 days > 15%)

_Paper research only. Past results do not predict future returns._
