---
name: fusion-council
description: Coordinate independent multi-model trading analysis, evidence-based debate, dissent preservation, risk-aware voting and auditable paper-trading decisions for BND AI Trading Engine & Management.
---

# BND Fusion Council

## Mission
Coordinate six independent AI participants: GPT, Claude, Gemini, Grok, DeepSeek and a local AI. Provider availability and model capabilities must be verified before execution. No participant may invent market data, tool results or model responses.

## Markets and horizons
- Markets: crypto, Forex, equities and commodities.
- Strategies: scalping, day trading and multi-day positions, long and short.
- Historical research: at least five years where available, preferably longer.
- Recent market context: three to six months.
- Use live data only with timestamps, provenance and freshness checks.
- Prevent look-ahead bias, leakage and overfitting.

## Independent analysis
Each participant receives the same versioned evidence packet and analyzes it independently before seeing other opinions.
Each analysis must include:
- Proposed action: LONG, SHORT or NO_TRADE.
- Thesis, supporting evidence and invalidation conditions.
- Confidence with uncertainty and limitations.
- Proposed entry, exit and time horizon when applicable.
- Estimated fees, spread, slippage and funding where relevant.
- Risks, alternative scenarios and missing information.

## Debate and minority protection
1. Record every initial opinion and vote.
2. Reveal independent analyses to the council.
3. Invite evidence-based criticism and counterarguments.
4. Preserve dissenting opinions, even when supported by only one participant.
5. A well-supported minority argument must trigger reconsideration by the other participants.
6. Allow participants to revise their votes with explicit reasons.
7. Store initial votes, revised votes, evidence and unresolved disagreements.
8. Never force consensus or fabricate agreement.

## Decision rules
Evaluate simple majority, evidence-weighted consensus and unanimity.
Model weights must be validated empirically, not assigned from reputation alone.
Correlated model errors must not be mistaken for independent confirmation.
NO_TRADE is a valid outcome.
Unanimity may justify a modest risk adjustment only when historical and out-of-sample evidence supports it, within hard risk limits.

## Risk management
A deterministic risk engine has veto power over every council decision.
Enforce exposure, leverage, liquidity, concentration and drawdown limits.
Compare both absolute net profit and risk-adjusted returns.
Always account for transaction fees, spread, slippage and funding.
Never increase risk merely because more models agree.
No live trading is authorized during development or initial validation.

## Validation
Use historical backtests, walk-forward tests and out-of-sample evaluation.
Compare conservative, balanced and aggressive virtual portfolios.
After infrastructure and implementation are complete, conduct 16 calendar days of forward paper trading as an initial evaluation, not proof of profitability.
Compare performance against appropriate benchmarks.

## Efficiency and security
Use model routing, caching and selective context compression to reduce API costs.
Never compress away critical numeric evidence, timestamps or risk constraints.
Do not reuse stale market analyses as live signals.
Keep API keys out of prompts, logs and Git repositories.
Require explicit approval before any real-money trading capability is enabled.

## Audit record
Every council cycle must store:
- Evidence packet identifier and timestamp.
- Model/provider identifiers and configuration versions.
- Initial analysis and vote for each participant.
- Critiques, dissent and revised votes.
- Final decision and risk-engine verdict.
- Expected and actual costs where measurable.
- Subsequent paper-trading outcome when available.

## Implementation status
This file defines intended behavior only. It does not connect external models, execute trades or establish that any integration is operational.
