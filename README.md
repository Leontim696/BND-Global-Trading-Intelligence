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

Not yet implemented: market data ingestion, backtesting, and LIVE gateway mode.

## Quick start

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python -m src.bnd.paper_demo
```

The demo runs the full council → debate → risk → trade pipeline offline
with mock agents.

## Paid API calls

All OpenRouter calls are opt-in. The workflows under `.github/workflows`
that call paid models require manual dispatch with explicit confirmation
inputs, and an `OPENROUTER_API_KEY` secret with a provider-side spending limit.
