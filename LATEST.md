Latest run: `runs/2026-10-30T170647Z_41095595232_PORTFOLIO-etf_1d_selector` (source b681fa1, job success)

# BND backtest summary

## Verdict
**No evidence of an edge:** no strategy beat the simple equal-weight basket on out-of-sample Sharpe.

## Multi-market portfolio
- Markets: 23 (2 bond, 7 commodity, 2 crypto, 6 forex, 6 index)
- Out-of-sample from 2022-01-24T00:00:00+00:00
- Sizing volatility, portfolio volatility target 15.0%, max leverage 3.0x, financing 0.0%/yr, kill switch at 30.0% drawdown, shorts on

| # | Strategy | Return | CAGR | Sharpe | Max drawdown | Avg leverage | Fills | Financing | Kill switch | p-value (adjusted) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| 1 | selector | 27.09% | 5.16% | 0.42 | 29.87% | 2.82x | 2668 | 436.54 | – | 0.342 (0.342) |
| – | equal-weight basket (long, 1x) | 48.80% | 8.70% | 0.84 | 17.10% | 0.95x | 49 | – | – | – |

**In EUR, unhedged** (a EUR investor; dollar moves included):

| Strategy | Return | CAGR | Sharpe | Max drawdown |
| --- | ---: | ---: | ---: | ---: |
| selector | 29.20% | 5.53% | 0.41 | 36.54% |
| equal-weight basket | 51.28% | 9.08% | 0.79 | 14.57% |

**Largest daily moves (check for bad data):** ETHEREUM -42.3% on 2020-03-12 (35 days > 15%), BITCOIN -37.2% on 2020-03-12 (20 days > 15%), SILVER -28.5% on 2026-01-30 (2 days > 15%), CRUDE_OIL -25.3% on 2020-03-09 (5 days > 15%), NATURAL_GAS -24.9% on 2026-02-02 (7 days > 15%), COPPER -19.3% on 2025-07-30 (1 days > 15%)

**Profit by market (out-of-sample):** NASDAQ100 1,270, BROAD_COMMODITIES 960, JAPAN 801, SP500 677, GOLD 659, US20Y_BOND 565, EMERGING 530, NATURAL_GAS 427, CRUDE_OIL 174, AUDUSD 152, USDCAD 107, EURUSD 64, COPPER -28, GBPUSD -28, USDJPY -30, USDCHF -54, US10Y_NOTE -86, GERMANY -232, UK -340, BITCOIN -560, SILVER -561, AGRICULTURE -652, ETHEREUM -669

| Max leverage | Return | Sharpe | Max drawdown | Kill switch |
| ---: | ---: | ---: | ---: | --- |
| 1x | 10.97% | 0.40 | 12.44% | – |
| 2x | 24.51% | 0.48 | 21.94% | – |
| 3x | 27.09% | 0.42 | 29.87% | – |
| 5x | -12.47% | -0.23 | 30.87% | 2023-12-27 |

Cost stress: ×2 → -14.18% (Sharpe -0.32); ×3 → -13.52% (Sharpe -0.31)

_Paper research only. Past results do not predict future returns._
