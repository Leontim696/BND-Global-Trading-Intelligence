
---
name: smart-money-radar
description: Research and monitor historically successful early-buyer crypto wallets across Ethereum, Solana, Base and BNB Chain, detect emerging token activity and generate evidence-based alerts and paper-trading signals.
---

# BND Smart Money Radar

## Mission
Identify historically successful early crypto buyers, monitor their on-chain activity and detect emerging tokens attracting multiple independently successful wallets.

All signals are research hypotheses. No wallet is assumed to be profitable in the future merely because it was profitable historically.

## Supported chains
- Ethereum
- Solana
- Base
- BNB Chain

Use chain-specific indexing and decoding. Never assume that transactions or token contracts behave identically across chains.

## Wallet discovery
- Research historically successful early buyers of PEPE and other major memecoin launches.
- Identify an initial shortlist of 10 to 20 candidate wallets.
- Prioritize six wallets with independently verified repeated profits across multiple tokens.
- Analyze available on-chain transaction histories for those six wallets.
- Record wallet addresses, chain, evidence sources and analysis timestamps.
- Exclude fabricated, unverifiable or cherry-picked profitability claims.

## Wallet performance
Evaluate:
- Realized and unrealized profits separately.
- Entry timing relative to token creation and liquidity availability.
- Multiple profitable trades across different tokens.
- Position sizes, holding periods and exits.
- Gas, transaction fees, MEV and slippage.
- Losses, failed transactions and abandoned positions.
- Whether reported profits can be independently reconstructed.

Account for incomplete histories, multiple addresses and cross-chain attribution uncertainty.

## Early-launch detection
Monitor:
- Newly created tokens and liquidity pools.
- First liquidity events and earliest swaps.
- Buys by monitored wallets shortly after launch.
- Multiple monitored wallets buying the same token.
- Repeated wallet combinations across launches.
- Developer funding links where supported by verifiable on-chain evidence.
- Liquidity concentration, holder distribution and contract permissions.

Do not classify ordinary coincidental purchases as coordinated activity without supporting evidence.

## Wallet clustering
Build evidence-based relationships using:
- Direct transfers and funding paths.
- Repeated transaction timing patterns.
- Shared deployer or funding sources.
- Cross-chain bridge evidence.
- Repeated participation in the same launches.

Distinguish confirmed on-chain links from statistical associations.
Do not claim real-world identities without reliable public evidence.

## Suspected insider-risk category
Maintain a separate risk-labeled watchlist for wallet clusters exhibiting suspicious early-launch behavior.

Examples discussed for research include publicly reported TRUMP, HAWK and LIBRA early-buyer cases.

Use neutral language such as suspected or potentially coordinated.
Do not treat suspicious patterns as proof of unlawful conduct.
This category is restricted to alerts, investigation and paper trading only.

## Alerts
Generate high-priority alerts when:
- Multiple monitored wallets buy the same newly launched token.
- A historically successful wallet enters a token unusually early.
- A recurring wallet cluster appears in another launch.
- Material liquidity or contract risks emerge.

Every alert must include:
- Chain and token contract address.
- Wallet addresses and transaction hashes.
- Timestamps and evidence sources.
- Liquidity and risk indicators.
- Confidence and uncertainty.
- Reason for the alert.

Avoid duplicate notifications and stale alerts.

## Paper-trading simulation
- Simulate entries and exits without using real funds.
- Use realistic execution timing and available liquidity.
- Include gas, fees, slippage, MEV and failed transactions.
- Never assume fills at prices unavailable to the strategy.
- Prevent look-ahead bias and survivorship bias.
- Compare performance against simple benchmarks.
- Apply BND Risk Auditor controls before virtual orders.

The proposed starting balance of EUR 10,000 is not confirmed and must not be treated as an approved setting.

## Integration
- Provide verified observations to BND Quant Research.
- Submit candidate signals to BND Fusion Council.
- Require deterministic BND Risk Auditor approval.
- Deliver alerts to the user's iPhone through a configured notification channel.
- Preserve evidence and audit trails for every signal.

## Security and operational limits
- Keep API keys and credentials outside Git.
- Respect provider rate limits and data licensing.
- Do not expose private personal information.
- Do not perform real-money trades.
- Do not attempt market manipulation or coordinate trading activity.

## Implementation status
This file is a design specification. It does not connect to blockchains, identify live wallets, send notifications or execute paper trades until the relevant software is implemented and tested.
