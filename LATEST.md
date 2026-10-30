Latest run: `runs/2026-10-30T164225Z_41091872216_PORTFOLIO-etf_1d_combo` (source ed13f09, job success)

# BND backtest summary

## Verdict
**No evidence of an edge:** no strategy beat the simple equal-weight basket on out-of-sample Sharpe.

## Multi-market portfolio
- Markets: 23 (2 bond, 7 commodity, 2 crypto, 6 forex, 6 index)
- Out-of-sample from 2022-01-24T00:00:00+00:00
- Sizing volatility, portfolio volatility target 15.0%, max leverage 3.0x, financing 0.0%/yr, kill switch at 30.0% drawdown, shorts on

| # | Strategy | Return | CAGR | Sharpe | Max drawdown | Avg leverage | Fills | Financing | Kill switch | p-value (adjusted) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| 1 | combo | 50.75% | 9.00% | 0.71 | 17.31% | 2.72x | 4069 | 370.99 | – | 0.634 (0.634) |
| – | equal-weight basket (long, 1x) | 48.80% | 8.70% | 0.84 | 17.10% | 0.95x | 49 | – | – | – |

**In EUR, unhedged** (a EUR investor; dollar moves included):

| Strategy | Return | CAGR | Sharpe | Max drawdown |
| --- | ---: | ---: | ---: | ---: |
| combo | 53.26% | 9.38% | 0.65 | 26.17% |
| equal-weight basket | 51.28% | 9.08% | 0.79 | 14.57% |

**Largest daily moves (check for bad data):** ETHEREUM -42.3% on 2020-03-12 (35 days > 15%), BITCOIN -37.2% on 2020-03-12 (20 days > 15%), SILVER -28.5% on 2026-01-30 (2 days > 15%), CRUDE_OIL -25.3% on 2020-03-09 (5 days > 15%), NATURAL_GAS -24.9% on 2026-02-02 (7 days > 15%), COPPER -19.3% on 2025-07-30 (1 days > 15%)

**What each combo member adds** (combo: Sharpe 0.71, return 50.75%):

| Member | Alone: return | Alone: Sharpe | Combo without it: return | Combo without it: Sharpe |
| --- | ---: | ---: | ---: | ---: |
| regime_switch | 9.12% | 0.20 | 77.22% | 0.88 |
| momentum | 47.33% | 0.64 | 1.23% | 0.09 |
| bollinger_reversion | -1.55% | 0.06 | 33.85% | 0.47 |

**Profit by market (out-of-sample):** SP500 992, SILVER 958, NASDAQ100 871, JAPAN 868, NATURAL_GAS 662, BITCOIN 596, CRUDE_OIL 561, EMERGING 423, GBPUSD 365, GERMANY 328, BROAD_COMMODITIES 284, US20Y_BOND 240, UK 172, AGRICULTURE 91, USDJPY 33, USDCHF 32, EURUSD -67, US10Y_NOTE -75, AUDUSD -191, USDCAD -346, ETHEREUM -399, GOLD -442, COPPER -509

| Max leverage | Return | Sharpe | Max drawdown | Kill switch |
| ---: | ---: | ---: | ---: | --- |
| 1x | 11.40% | 0.47 | 9.73% | – |
| 2x | 34.31% | 0.66 | 16.19% | – |
| 3x | 50.75% | 0.71 | 17.31% | – |
| 5x | 55.10% | 0.66 | 19.20% | – |

Cost stress: ×2 → 30.20% (Sharpe 0.48); ×3 → 12.23% (Sharpe 0.25)

_Paper research only. Past results do not predict future returns._
