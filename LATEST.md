Latest run: `runs/2026-11-01T103542Z_41298099426_BTCUSDT_4h_all` (source ca827e5, job success)

# BND backtest summary

## Dataset
- File: `backtest-reports/BTCUSDT-4h.csv` (17163 candles, 4 gaps)
- Range: 2019-01-01T00:00:00+00:00 → 2026-11-01T04:00:00+00:00
- SHA-256: `476bee91836e01d63625ddeeb7fc5c928d31bd847f6dd95a1869e37c06510dd0`

## Verdict
**No strategy shows evidence of an edge** after adjusting for testing all of them at once. Treat any profit below as luck.

## Strategy comparison (out-of-sample, default parameters)

| # | Strategy | Return | Sharpe | Max drawdown | Trades | Capital invested | p-value (adjusted) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | regime_switch | 5.39% | 0.89 | 1.84% | 24 | 1.36% | 0.139 (1.000) |
| 2 | ema_crossover | 5.09% | 0.67 | 4.23% | 15 | 2.28% | 0.317 (1.000) |
| 3 | donchian_breakout | 5.99% | 0.55 | 5.44% | 34 | 6.56% | 0.188 (1.000) |
| 4 | sma_crossover | 1.18% | 0.11 | 8.09% | 60 | 10.36% | 0.495 (1.000) |
| 5 | macd | -3.71% | -0.23 | 14.11% | 194 | 10.13% | 0.356 (1.000) |
| 6 | adx_trend | -2.44% | -0.23 | 6.83% | 94 | 4.64% | 0.446 (1.000) |
| 7 | keltner_breakout | -2.36% | -0.23 | 10.07% | 60 | 4.16% | 0.663 (1.000) |
| 8 | momentum | -6.84% | -0.55 | 12.60% | 91 | 9.35% | 0.703 (1.000) |
| 9 | bollinger_reversion | -5.43% | -0.62 | 8.68% | 92 | 3.70% | 0.396 (1.000) |
| 10 | rsi_reversion | -4.61% | -0.64 | 6.09% | 38 | 2.18% | 0.535 (1.000) |
| 11 | volatility_target | -1.05% | -0.65 | 1.49% | 1 | 0.18% | 0.673 (1.000) |
| 12 | stochastic_reversion | -8.51% | -0.82 | 10.66% | 121 | 5.14% | 0.653 (1.000) |
| – | buy & hold | 25.55% | 0.44 | 53.45% | 1 | 100.00% | – |

## Walk-forward (SMA long/flat, independent folds)
- Folds: 32, beating buy & hold: 11
- Excess return per fold: mean -8.45 pp, median -5.98 pp

_Paper research only. Past results do not predict future returns._
