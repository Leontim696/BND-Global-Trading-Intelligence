# Controlled AI connectivity smoke test

The gateway remains MOCK-only. This script is an **isolated manual connectivity test**, not a live trading system, automated council, or proof of profitable trading.

## Requirements

1. Configure an OpenRouter API key in your trusted local environment, never in the repository.
2. Set the exact model ID using `BND_MODEL_CLAUDE` (or `BND_MODEL_GPT`, `BND_MODEL_GEMINI`, `BND_MODEL_DEEPSEEK`, `BND_MODEL_GROK`).
3. Set a provider-side spending limit before testing. This script does not reserve or cap spending in SQLite; it makes one API request only when invoked.
4. Explicitly set `BND_ALLOW_LIVE_AI=true`.
5. Run `python -m src.bnd.ai_smoke_test --agent claude --confirm-paid-api-call`.

Do not store secrets in GitHub Actions logs or commit them. The request intentionally contains no live market data; a HOLD vote is expected. An actual provider response and token usage must be observed before claiming live connectivity. No orders are placed.
