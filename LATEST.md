Latest run: `runs/2026-10-30T180133Z_41102944352_PORTFOLIO-etf_1d_cross_momentum` (source b9624e4, job success)

# BND backtest summary

## Verdict
**No evidence of an edge:** no strategy beat the simple equal-weight basket on out-of-sample Sharpe.

## Multi-market portfolio
- Markets: 23 (2 bond, 7 commodity, 2 crypto, 6 forex, 6 index)
- Out-of-sample from 2022-01-24T00:00:00+00:00
- Sizing volatility, portfolio volatility target 15.0%, max leverage 3.0x, financing 0.0%/yr, kill switch at 30.0% drawdown, shorts on

| # | Strategy | Return | CAGR | Sharpe | Max drawdown | Avg leverage | Fills | Financing | Kill switch | p-value (adjusted) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| 1 | cross_momentum | 43.44% | 7.87% | 0.57 | 23.17% | 2.70x | 2317 | 636.26 | – | 1.000 (1.000) |
| – | equal-weight basket (long, 1x) | 48.80% | 8.70% | 0.84 | 17.10% | 0.95x | 49 | – | – | – |

**In EUR, unhedged** (a EUR investor; dollar moves included):

| Strategy | Return | CAGR | Sharpe | Max drawdown |
| --- | ---: | ---: | ---: | ---: |
| cross_momentum | 45.83% | 8.24% | 0.53 | 31.95% |
| equal-weight basket | 51.28% | 9.08% | 0.79 | 14.57% |

**Largest daily moves (check for bad data):** ETHEREUM -42.3% on 2020-03-12 (35 days > 15%), BITCOIN -37.2% on 2020-03-12 (20 days > 15%), SILVER -28.5% on 2026-01-30 (2 days > 15%), CRUDE_OIL -25.3% on 2020-03-09 (5 days > 15%), NATURAL_GAS -24.9% on 2026-02-02 (7 days > 15%), COPPER -19.3% on 2025-07-30 (1 days > 15%)

**Profit by market (out-of-sample):** BITCOIN 1,456, GOLD 1,203, SILVER 1,160, EMERGING 1,037, SP500 989, NASDAQ100 719, UK 387, AGRICULTURE 374, NATURAL_GAS 291, JAPAN 246, BROAD_COMMODITIES 231, USDJPY 140, EURUSD 85, GERMANY -50, AUDUSD -65, US20Y_BOND -152, GBPUSD -232, COPPER -306, USDCHF -356, CRUDE_OIL -361, ETHEREUM -408, USDCAD -460, US10Y_NOTE -949

| Max leverage | Return | Sharpe | Max drawdown | Kill switch |
| ---: | ---: | ---: | ---: | --- |
| 1x | 16.54% | 0.55 | 11.19% | – |
| 2x | 32.37% | 0.56 | 22.11% | – |
| 3x | 43.44% | 0.57 | 23.17% | – |
| 5x | 36.67% | 0.47 | 26.04% | – |

Cost stress: ×2 → 25.26% (Sharpe 0.38); ×3 → 9.10% (Sharpe 0.20)

_Paper research only. Past results do not predict future returns._
