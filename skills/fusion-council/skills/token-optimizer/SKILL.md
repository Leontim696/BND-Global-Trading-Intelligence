
---
name: token-optimizer
description: Optimize multi-provider AI token usage and API costs for BND AI Trading Engine without compromising trading evidence, independent analysis, or risk controls.
---

# BND Token Optimizer

## Mission
Minimize unnecessary AI API costs while preserving analytical accuracy, independent reasoning, auditability, and trading safety.

## Supported providers
- OpenRouter
- NVIDIA NIM
- Baseten
- Direct provider APIs when explicitly configured

## Model routing
- Select models based on task complexity, quality, latency, availability and cost.
- Use inexpensive or local models for routine classification and formatting.
- Use stronger models for difficult research, code audits and critical decisions.
- Benchmark model performance before assigning permanent roles.
- Do not automatically use the cheapest model.
- Use deterministic Python calculations instead of LLM calls for indicators, position sizing and financial arithmetic.

## Context optimization
- Send relevant, structured evidence rather than full raw datasets.
- Preserve numerical values, units, timestamps, provenance and uncertainty.
- Summarize historical information separately from live market observations.
- Apply context compression only after validating that critical facts survive.
- Never compress away risk constraints or contradictory evidence.

## Caching
- Cache immutable research, documentation and historical calculations.
- Reuse identical deterministic results when inputs and versions match.
- Include data version, model version, prompt version and parameters in cache keys.
- Apply freshness limits to news, prices, order books and sentiment.
- Never treat a cached trading recommendation as a current live signal without revalidation.
- Avoid semantic caching for trade decisions unless equivalence and freshness are rigorously established.

## Independent council analysis
- All council participants must receive the same versioned factual evidence packet.
- Do not share another participant's reasoning before the independent analysis stage.
- Do not remove dissenting evidence to save tokens.
- Debate rounds should be targeted to unresolved disagreements.
- Preserve initial and revised votes, reasons and model identities.
- A minority argument with strong evidence must receive substantive reconsideration.

## Cost management
- Record input tokens, output tokens, provider, model, latency and estimated USD cost per request.
- Track costs per council cycle, strategy, market and day.
- Support configurable daily and monthly spending limits.
- Warn before reaching spending thresholds.
- Stop optional requests when budgets are exhausted.
- Never silently bypass hard budget limits.
- Account for provider fees, retries and cache behavior when calculating actual costs.

## Quality validation
- Compare optimized and unoptimized workflows on the same historical test cases.
- Measure factual accuracy, signal quality, dissent preservation, latency and total cost.
- Reject optimizations that materially worsen decision quality or risk compliance.
- Evaluate absolute net returns and risk-adjusted returns separately.
- Include trading fees, spread, slippage and funding in financial performance tests.

## Security
- Never place API keys in Git, prompts, logs or public dashboards.
- Use environment variables or an appropriate secrets manager.
- Restrict external tool permissions and validate third-party repositories.
- No automatic real-money trading.

## Implementation status
This document specifies intended optimization behavior. It does not install LiteLLM, activate caching, connect APIs or guarantee token savings.
