# BND backtest summary

## Dataset
- File: `backtest-reports/BTCUSDT-1d.csv` (1399 candles, 0 gaps)
- Range: 2023-01-01T00:00:00+00:00 → 2026-10-30T00:00:00+00:00
- SHA-256: `22294bcb5f983928aa967609c99d8139b674c03cf749ece482503f107ab70951`

## Verdict
No robustness report: no conclusion about an edge is possible.

Out-of-sample, risk-adjusted: Sharpe 0.30 vs -0.51 for buy & hold; max drawdown 28.98% vs 52.97%; return 5.26% vs -30.29% with 51.67% average capital invested.

## Backtest: `sma_crossover`
Costs per fill: fee 0.1%, slippage 0.05%; funding 0.0%/yr on open positions; cash interest 0.0%/yr; shorts off.

**full** (2023-01-01T00:00:00+00:00 → 2026-10-30T00:00:00+00:00, risk gate: disabled_research_only)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Net profit | 9,119.09 | 36,420.07 |
| Return | 91.19% | 364.20% |
| CAGR | 18.44% | 49.30% |
| Max drawdown | 38.71% | 52.97% |
| Volatility | 33.30% | 46.16% |
| Sharpe | 0.67 | 1.10 |
| Sortino | 1.05 | 1.71 |
| Calmar | 0.48 | 0.93 |
| Expectancy per trade | 569.94 | 36,420.07 |
| Turnover (x equity / yr) | 8.26 | 0.36 |
| Trades | 16 | 1 |
| Time in market | 57.04% | 99.93% |
| Avg capital exposure | 57.04% | 99.93% |
| Funding paid | 0.00 | 0.00 |
| Interest earned | 0.00 | 0.00 |
| Entries vetoed by risk engine | 0 | 0 |

**in_sample** (2023-01-01T00:00:00+00:00 → 2025-09-05T00:00:00+00:00, risk gate: disabled_research_only)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Net profit | 8,164.06 | 56,394.28 |
| Return | 81.64% | 563.94% |
| CAGR | 24.94% | 102.64% |
| Max drawdown | 38.71% | 28.10% |
| Volatility | 35.45% | 47.38% |
| Sharpe | 0.80 | 1.73 |
| Sortino | 1.26 | 2.81 |
| Calmar | 0.64 | 3.65 |
| Expectancy per trade | 742.19 | 56,394.28 |
| Turnover (x equity / yr) | 8.15 | 0.78 |
| Trades | 11 | 1 |
| Time in market | 59.35% | 99.90% |
| Avg capital exposure | 59.35% | 99.90% |
| Funding paid | 0.00 | 0.00 |
| Interest earned | 0.00 | 0.00 |
| Entries vetoed by risk engine | 0 | 0 |

**out_of_sample** (2025-09-06T00:00:00+00:00 → 2026-10-30T00:00:00+00:00, risk gate: disabled_research_only)

| Metric | Strategy | Buy & hold |
| --- | ---: | ---: |
| Net profit | 525.78 | -3,029.37 |
| Return | 5.26% | -30.29% |
| CAGR | 4.56% | -26.94% |
| Max drawdown | 28.98% | 52.97% |
| Volatility | 27.69% | 43.02% |
| Sharpe | 0.30 | -0.51 |
| Sortino | 0.45 | -0.72 |
| Calmar | 0.16 | -0.51 |
| Expectancy per trade | 105.16 | -3,029.37 |
| Turnover (x equity / yr) | 8.44 | 1.99 |
| Trades | 5 | 1 |
| Time in market | 51.67% | 100.00% |
| Avg capital exposure | 51.67% | 100.00% |
| Funding paid | 0.00 | 0.00 |
| Interest earned | 0.00 | 0.00 |
| Entries vetoed by risk engine | 0 | 0 |

## Missing reports
- `backtest-reports/walk-forward.json`: JSONDecodeError

_Paper research only. Past results do not predict future returns._
