
---
name: risk-auditor
description: Independently evaluate, approve, reduce or veto proposed BND AI Trading Engine paper trades using deterministic portfolio risk controls and evidence-based dynamic risk management.
---

# BND Risk Auditor

## Mission
Protect BND AI Trading Engine & Management against unacceptable trading risks while allowing measured, evidence-based risk taking that can improve profitability.

The Risk Auditor is independent of the Fusion Council. No AI vote, including unanimity, can override a hard risk limit.

## Scope
- Crypto, Forex, equities and commodities.
- Scalping, day trading and multi-day positions.
- Long and short strategies.
- Conservative, balanced and aggressive virtual portfolios.
- Paper trading only during development and initial evaluation.

## Mandatory risk checks
Before approving any proposed trade, verify:
- Available virtual capital and margin.
- Position size and maximum possible loss.
- Portfolio exposure and concentration.
- Correlation with existing positions.
- Leverage and liquidation risk.
- Market liquidity, spread and slippage.
- Transaction fees, funding and borrowing costs.
- Volatility and market regime.
- Maximum portfolio drawdown and daily loss limits.
- Data freshness, integrity and broker constraints.

Missing critical data must produce NO_TRADE or a request for additional evidence.

## Dynamic risk allocation
Risk must not be permanently minimized to zero.
Evaluate whether modest increases in position risk improve both absolute net returns and risk-adjusted performance.

Dynamic risk adjustments require:
1. Reliable historical evidence.
2. Out-of-sample validation.
3. Acceptable drawdown and tail-risk estimates.
4. Adequate liquidity and execution quality.
5. Compliance with all hard risk limits.

AI unanimity alone is never sufficient to increase risk.

## Hard safety limits
The implementation must define explicit numerical limits for:
- Maximum risk per trade.
- Maximum daily portfolio loss.
- Maximum total drawdown.
- Maximum gross and net exposure.
- Maximum leverage.
- Maximum correlated exposure.
- Minimum liquidity and data-quality requirements.

These values must be approved before paper trading begins.
Never invent default limits or silently disable a configured limit.

## Council interaction
Receive the Fusion Council decision and all supporting evidence.
Review initial votes, revised votes and unresolved dissent.
Evaluate minority warnings even when the majority disagrees.
Issue one of:
- APPROVE
- APPROVE_REDUCED
- REJECT
- REQUEST_MORE_DATA

Record the reason for every decision.
Risk approval must be reproducible using deterministic calculations.

## Cost-aware performance
Evaluate both:
- Absolute net profit.
- Risk-adjusted returns.

Include commissions, spreads, slippage, funding and borrowing costs.
Do not reject otherwise attractive strategies merely because transaction costs are high; evaluate their impact on expected net profitability.

## Stress testing
Test portfolio behavior under:
- Sudden price gaps and volatility spikes.
- Liquidity shortages.
- Exchange or broker outages.
- Correlated market crashes.
- Unexpected funding and spread increases.
- Stale data and delayed execution.
- Model failures and conflicting AI recommendations.

## Emergency controls
Provide deterministic mechanisms for:
- Blocking new orders.
- Suspending a strategy.
- Disabling an affected market or broker connection.
- Cancelling outstanding virtual orders where supported.
- Recording incidents and requiring explicit recovery approval.

## Audit logging
Record:
- Timestamp and evidence version.
- Proposed trade and council decision.
- Portfolio state before evaluation.
- Risk calculations and configured limits.
- Approval, reduction or rejection.
- Final virtual order and execution result.
- Subsequent risk and performance outcomes.

## Validation
Test risk controls independently from AI models.
Use unit tests, historical scenarios and simulated failures.
Ensure every hard limit triggers the expected veto.
Never use an LLM as the sole enforcement mechanism.

## Security and implementation status
Keep credentials and API keys outside Git repositories.
Never enable real-money trading automatically.
This document defines intended behavior only; it does not implement or activate a functioning risk engine.
