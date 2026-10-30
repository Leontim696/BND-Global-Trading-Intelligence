# BND backtest summary

## Dataset
- File: `backtest-reports/BTCUSDT-1d.csv` (2859 candles, 0 gaps)
- Range: 2019-01-01T00:00:00+00:00 → 2026-10-29T00:00:00+00:00
- SHA-256: `64207ddad540a3ade72544eefb9ae0fc1d08d6117590ac4c264407506662a4cc`

## Verdict
**No strategy shows evidence of an edge** after adjusting for testing all of them at once. Treat any profit below as luck.

## Strategy comparison (out-of-sample, default parameters)

| # | Strategy | Return | Sharpe | Max drawdown | Trades | Capital invested | p-value (adjusted) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | sma_crossover | 48.96% | 0.70 | 28.01% | 11 | 55.71% | 0.198 (1.000) |
| 2 | momentum | 51.73% | 0.67 | 28.10% | 8 | 61.19% | 0.317 (1.000) |
| 3 | ema_crossover | 30.91% | 0.54 | 30.95% | 16 | 52.68% | 0.416 (1.000) |
| 4 | macd | 18.48% | 0.39 | 34.12% | 35 | 49.88% | 0.386 (1.000) |
| 5 | volatility_target | 16.60% | 0.36 | 51.42% | 1 | 86.75% | 0.762 (1.000) |
| 6 | donchian_breakout | 13.50% | 0.34 | 29.84% | 8 | 36.48% | 0.545 (1.000) |
| 7 | rsi_reversion | 10.57% | 0.30 | 23.03% | 6 | 17.72% | 0.346 (1.000) |
| 8 | bollinger_reversion | 7.16% | 0.24 | 37.60% | 15 | 24.71% | 0.386 (1.000) |
| – | buy & hold | 23.02% | 0.42 | 52.97% | 1 | 100.00% | – |

## Walk-forward (SMA long/flat, independent folds)
- Folds: 3, beating buy & hold: 1
- Excess return per fold: mean -13.20 pp, median -25.05 pp

_Paper research only. Past results do not predict future returns._
