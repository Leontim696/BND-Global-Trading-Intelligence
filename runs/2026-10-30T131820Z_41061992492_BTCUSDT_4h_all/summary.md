# BND backtest summary

## Dataset
- File: `backtest-reports/BTCUSDT-4h.csv` (17152 candles, 4 gaps)
- Range: 2019-01-01T00:00:00+00:00 → 2026-10-30T08:00:00+00:00
- SHA-256: `5e094c7ec53092a0b91904e9904213c85c5469b2ac662b6235d375fb9748246d`

## Verdict
**No strategy shows evidence of an edge** after adjusting for testing all of them at once. Treat any profit below as luck.

## Strategy comparison (out-of-sample, default parameters)

| # | Strategy | Return | Sharpe | Max drawdown | Trades | Capital invested | p-value (adjusted) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | volatility_target | -1.35% | 0.18 | 55.53% | 1 | 89.18% | 0.644 (1.000) |
| 2 | donchian_breakout | -14.01% | -0.02 | 43.65% | 66 | 60.09% | 0.505 (1.000) |
| 3 | sma_crossover | -57.50% | -0.63 | 63.73% | 121 | 98.07% | 0.495 (1.000) |
| 4 | momentum | -57.03% | -0.65 | 69.75% | 183 | 94.77% | 0.475 (1.000) |
| 5 | bollinger_reversion | -51.57% | -0.67 | 58.31% | 189 | 55.92% | 0.327 (1.000) |
| 6 | rsi_reversion | -48.18% | -0.71 | 54.80% | 77 | 38.38% | 0.604 (1.000) |
| 7 | macd | -68.85% | -0.91 | 75.80% | 387 | 98.62% | 0.307 (1.000) |
| 8 | ema_crossover | -84.08% | -1.61 | 86.23% | 205 | 97.38% | 0.951 (1.000) |
| – | buy & hold | 30.09% | 0.47 | 53.45% | 1 | 100.00% | – |

## Walk-forward (SMA long/flat, independent folds)
- Folds: 32, beating buy & hold: 11
- Excess return per fold: mean -8.45 pp, median -5.98 pp

_Paper research only. Past results do not predict future returns._
