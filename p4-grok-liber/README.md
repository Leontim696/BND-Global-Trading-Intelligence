# BND paper trading (virtual money)

- Run: 2026-11-15T02:12:59.165774+00:00 | strategy `ai_council`
- Equity: 11,668.63 USD (start 11,183.00, +4.34%)
- Gross leverage: 0.33x | candles processed: 60
- Kill switch: off

## Positions

| Market | Quantity | Avg price | Last | Value | Weight | P&L | Stop |
|---|---:|---:|---:|---:|---:|---:|---:|
| AAVE | -1.1931 | 123.5682 | 100.6600 | -120.09 | -1.0% | +27.33 | 151.9771 |
| ALGO | -929.3757 | 0.0955 | 0.0776 | -72.12 | -0.6% | +16.59 | 0.1164 |
| APT | -198.7092 | 0.5354 | 0.4496 | -89.34 | -0.8% | +17.06 | 0.6838 |
| ARB | -552.8362 | 0.1517 | 0.1281 | -70.82 | -0.6% | +13.06 | 0.1965 |
| BA | -1.5163 | 173.4180 | 171.5000 | -260.04 | -2.2% | +2.91 | 191.3872 |
| BITCOIN | -0.0042 | 71307.2973 | 68249.2734 | -286.05 | -2.5% | +12.82 | 78151.3596 |
| BNB | -0.4594 | 655.7253 | 629.4333 | -289.14 | -2.5% | +12.08 | 718.8530 |
| BONK | -39517214.5899 | 0.0000 | 0.0000 | -91.28 | -0.8% | +16.83 | 0.0000 |
| CRV | -556.9984 | 0.2312 | 0.2036 | -113.40 | -1.0% | +15.36 | 0.2954 |
| ETC | -16.5320 | 6.9065 | 5.8100 | -96.05 | -0.8% | +18.13 | 8.0296 |
| GOLD | -1.0319 | 357.4927 | 355.4500 | -366.79 | -3.1% | +2.11 | 385.7472 |
| KO | 5.6478 | 98.2795 | 99.2500 | 560.54 | +4.8% | +5.48 | 92.2326 |
| LDO | -292.0219 | 0.3154 | 0.2676 | -78.15 | -0.7% | +13.97 | 0.3927 |
| POL | -1601.2597 | 0.0873 | 0.0787 | -126.07 | -1.1% | +13.72 | 0.1036 |
| RENK | -6.9491 | 34.6696 | 32.7600 | -227.65 | -2.0% | +13.27 | 39.0655 |
| SEI | -2242.6976 | 0.0469 | 0.0377 | -84.46 | -0.7% | +20.63 | 0.0587 |
| SHIB | -46350092.0736 | 0.0000 | 0.0000 | -177.98 | -1.5% | +18.71 | 0.0000 |
| SILVER | -4.9170 | 45.4664 | 44.1300 | -216.99 | -1.9% | +6.57 | 51.2534 |
| STX | -382.5720 | 0.2851 | 0.2631 | -100.65 | -0.9% | +8.40 | 0.3747 |
| SUI | -87.8234 | 0.8412 | 0.7011 | -61.57 | -0.5% | +12.30 | 1.0360 |
| TIA | -220.4953 | 0.3845 | 0.3452 | -76.11 | -0.7% | +8.67 | 0.5462 |
| TRX | -894.3132 | 0.3167 | 0.3069 | -274.46 | -2.4% | +8.80 | 0.3364 |
| UNI | -14.0485 | 6.2289 | 4.8880 | -68.67 | -0.6% | +18.84 | 7.9952 |

## Orders for the next open

| Market | Side | Weight now -> target | Status | Note |
|---|---|---|---|---|
| EURUSD | SELL | +0.0% -> -24.2% | PENDING |  |
| BITCOIN | BUY | -2.5% -> +0.0% | PENDING |  |
| BNB | BUY | -2.5% -> +0.0% | PENDING |  |
| GOOGL | SELL | +0.0% -> -3.1% | PENDING |  |
| WMT | BUY | +0.0% -> +4.8% | PENDING |  |
| KO | SELL | +4.8% -> +0.0% | PENDING |  |
| CAT | SELL | +0.0% -> -2.6% | PENDING |  |
| L3HARRIS | BUY | +0.0% -> +3.9% | PENDING |  |
| AVAX | SELL | +0.0% -> -1.1% | PENDING |  |
| SHIB | BUY | -1.5% -> +0.0% | PENDING |  |
| UNI | BUY | -0.6% -> +0.0% | PENDING |  |
| AAVE | BUY | -1.0% -> +0.0% | PENDING |  |
| ICP | SELL | +0.0% -> -1.3% | PENDING |  |
| ETC | BUY | -0.8% -> +0.0% | PENDING |  |
| APT | BUY | -0.8% -> +0.0% | PENDING |  |
| ATOM | SELL | +0.0% -> -1.4% | PENDING |  |
| ARB | BUY | -0.6% -> +0.0% | PENDING |  |
| ALGO | BUY | -0.6% -> +0.0% | PENDING |  |
| INJ | SELL | +0.0% -> -1.0% | REJECTED | Extreme gap on the last bar: no new risk |
| RENDER | SELL | +0.0% -> -1.3% | PENDING |  |
| BONK | BUY | -0.8% -> +0.0% | PENDING |  |
| JUP | SELL | +0.0% -> -1.1% | PENDING |  |

## Stress scenarios (instant shock to current positions)

| Scenario | Equity change | Biggest loser | Kill switch |
|---|---:|---|---|
| Sharp dollar rally | +2.4% | KO | no |
| One-day crash like October 1987 | +6.0% | KO | no |
| Crypto collapse within a week | +9.7% | KO | no |
| Covid crash, Feb-Mar 2020 | +10.3% | KO | no |
| Inflation and rate hikes, Jan-Oct 2022 | +14.3% | KO | no |
| Global financial crisis, Sep-Nov 2008 | +14.7% | KO | no |

## Equity, last runs

| Run | Equity |
|---|---:|
| 2026-11-04 | 11,183.00 |
| 2026-11-04 | 11,178.14 |
| 2026-11-05 | 11,204.88 |
| 2026-11-06 | 11,409.88 |
| 2026-11-07 | 11,283.81 |
| 2026-11-08 | 11,304.63 |
| 2026-11-09 | 11,398.09 |
| 2026-11-10 | 11,315.91 |
| 2026-11-11 | 11,357.74 |
| 2026-11-12 | 11,357.68 |
| 2026-11-14 | 11,465.78 |
| 2026-11-15 | 11,668.63 |

_Virtual money only. Backtests found no proven edge; this record is the forward test, not proof of profit._
