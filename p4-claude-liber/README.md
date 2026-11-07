# BND paper trading (virtual money)

- Run: 2026-11-07T23:19:06.572853+00:00 | strategy `ai_council`
- Equity: 11,125.89 USD (start 11,183.00, -0.51%)
- Gross leverage: 0.43x | candles processed: 100
- Kill switch: off

## Positions

| Market | Quantity | Avg price | Last | Value | Weight | P&L | Stop |
|---|---:|---:|---:|---:|---:|---:|---:|
| BONK | -144335175.9261 | 0.0000 | 0.0000 | -409.91 | -3.7% | -3.50 | 0.0000 |
| ENA | -1861.1214 | 0.1603 | 0.1637 | -304.67 | -2.7% | -6.29 | 0.2237 |
| FLOKI | -22963797.9411 | 0.0000 | 0.0000 | -497.17 | -4.5% | -13.59 | 0.0000 |
| ICP | -181.7841 | 2.3988 | 2.4330 | -442.28 | -4.0% | -6.22 | 2.9563 |
| OP | -2956.0838 | 0.1012 | 0.1054 | -311.57 | -2.8% | -12.27 | 0.1342 |
| US10Y_NOTE | 30.3701 | 91.8292 | 91.8600 | 2,789.80 | +25.1% | +0.94 | 90.5267 |

## Orders for the next open

| Market | Side | Weight now -> target | Status | Note |
|---|---|---|---|---|
| US10Y_NOTE | SELL | +25.1% -> +0.0% | PENDING |  |
| XLM | SELL | +0.0% -> -20.5% | PENDING | capped by risk at the stop |
| ICP | BUY | -4.0% -> +0.0% | PENDING |  |
| OP | BUY | -2.8% -> +0.0% | PENDING |  |
| BONK | BUY | -3.7% -> +0.0% | PENDING |  |
| FLOKI | BUY | -4.5% -> +0.0% | PENDING |  |
| ENA | BUY | -2.7% -> +0.0% | PENDING |  |

## Stress scenarios (instant shock to current positions)

| Scenario | Equity change | Biggest loser | Kill switch |
|---|---:|---|---|
| Sharp dollar rally | +1.8% | - | no |
| One-day crash like October 1987 | +6.1% | - | no |
| Inflation and rate hikes, Jan-Oct 2022 | +8.6% | US10Y_NOTE | no |
| Crypto collapse within a week | +8.8% | - | no |
| Covid crash, Feb-Mar 2020 | +10.1% | - | no |
| Global financial crisis, Sep-Nov 2008 | +14.4% | - | no |

## Equity, last runs

| Run | Equity |
|---|---:|
| 2026-11-04 | 11,183.00 |
| 2026-11-04 | 11,183.00 |
| 2026-11-05 | 11,207.40 |
| 2026-11-06 | 11,172.55 |
| 2026-11-07 | 11,125.89 |

_Virtual money only. Backtests found no proven edge; this record is the forward test, not proof of profit._
