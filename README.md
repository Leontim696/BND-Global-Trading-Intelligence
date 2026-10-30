# BND-Global-Trading-Intelligence

Multi-agent AI research and paper-trading infrastructure. No live orders
are ever placed.

## What exists today

| Module | Purpose |
| --- | --- |
| `fusion_council` | Five independent agent votes (GPT, Claude, Gemini, Grok, DeepSeek), revisions, strict-majority decision, audit log |
| `debate_engine` | Structured debate rounds; every agent must argue and respond before closing |
| `risk_engine` | Deterministic veto: leverage, daily loss, drawdown, exposure and per-trade risk limits |
| `trade_coordinator` | Combines a closed debate with risk checks into a paper-trade outcome |
| `ai_gateway` | Provider routing with budget reservations (MOCK mode only) |
| `openrouter_adapter` | Opt-in OpenRouter client returning validated BUY/SELL/HOLD analyses |
| `cost_tracker`, `cost_storage` | In-memory and SQLite token-cost accounting with daily/monthly budgets |
| `market_data` | Validated OHLCV candles, CSV storage, Binance public-data download |
| `backtester` | Next-open execution, fees, slippage, stop losses, risk-engine sizing, metrics |
| `strategies` | Baselines: buy-and-hold, SMA crossover, Donchian breakout |

Not yet implemented: walk-forward optimisation, AI-agent strategies in
backtests, and LIVE gateway mode.

## Quick start

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python -m src.bnd.paper_demo
```

The demo runs the full council → debate → risk → trade pipeline offline
with mock agents.

## Backtesting

```bash
python -m src.bnd.backtest_cli fetch --symbol BTCUSDT --interval 4h \
    --start 2019-01-01 --out data/BTCUSDT-4h.csv
python -m src.bnd.backtest_cli run --data data/BTCUSDT-4h.csv \
    --strategy sma_crossover --stop-loss 5 --risk-per-trade 1
```

Decisions use only past candles and fill at the next open, paying fees
and slippage (defaults: 0.10% and 0.05% per fill). Each report compares
the strategy with buy-and-hold for the full, in-sample (first 70%) and
out-of-sample periods. Judge a strategy by its out-of-sample results.
The "BND Backtest (manual)" workflow runs the same steps on GitHub.

## Paid API calls

All OpenRouter calls are opt-in. The workflows under `.github/workflows`
that call paid models require manual dispatch with explicit confirmation
inputs, and an `OPENROUTER_API_KEY` secret with a provider-side spending limit.
