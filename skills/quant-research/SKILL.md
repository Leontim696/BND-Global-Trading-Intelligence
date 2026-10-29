
---
name: quant-research
description: Research, backtest and validate multi-asset trading strategies for BND AI Trading Engine & Management using reproducible data, realistic costs and rigorous risk-adjusted evaluation.
---

# BND Quant Research

## Mission
Develop and evaluate trading strategies across crypto, Forex, equities and commodities. Optimize both absolute net profit and risk-adjusted returns while respecting hard risk limits.

## Markets
- Crypto: Bitcoin, Ethereum, altcoins and emerging tokens.
- Forex: major, minor and selected cross-currency pairs.
- Equities: individual stocks, ETFs and indices.
- Commodities: gold, silver, oil and other liquid instruments.
- Account for market-specific sessions, liquidity, leverage and contract specifications.

## Trading strategies
- Scalping: short holding periods with realistic execution assumptions.
- Day trading: intraday entries and exits.
- Swing trading: multi-day positions.
- Long and short positions where supported.
- Evaluate trend-following, mean-reversion, breakout, momentum and regime-dependent strategies.
- Avoid assuming one strategy works in every market condition.

## Historical research
- Use at least five years of historical data where available.
- Prefer ten or more years when reliable data exists.
- Examine bull markets, bear markets, sideways markets and volatility shocks.
- Use the most recent three to six months for current market context.
- Record data sources, timestamps, adjustments, missing periods and limitations.
- Never fabricate unavailable historical data.

## Data quality
- Validate OHLCV data, corporate actions, market calendars and instrument specifications.
- Detect missing candles, duplicates, outliers and inconsistent timestamps.
- Account for survivorship bias and delisted assets where relevant.
- For newly launched tokens, explicitly record limited history and liquidity.
- Separate historical, validation and live data.

## Backtesting
- Use Python-based deterministic calculations.
- Evaluate candidate frameworks such as vectorbt, backtesting.py and Qlib.
- Prevent look-ahead bias and future-data leakage.
- Use realistic spreads, trading fees, slippage, funding and borrowing costs.
- Model execution constraints, liquidity and partial fills where relevant.
- Include walk-forward and out-of-sample testing.
- Perform sensitivity and robustness analysis.
- Compare strategies against appropriate passive and simple active benchmarks.

## Performance metrics
- Absolute net profit and net return.
- Risk-adjusted return, including Sharpe and Sortino where appropriate.
- Maximum drawdown and recovery duration.
- Profit factor, win rate and payoff ratio.
- Exposure, turnover, volatility and tail risk.
- Transaction costs and their effect on profitability.
- Stability across market regimes and validation periods.

## Portfolio evaluation
Compare three virtual portfolios:
- Conservative.
- Balanced.
- Aggressive.

Allow evidence-based dynamic risk adjustment within hard exposure, leverage and loss caps.
Evaluate diversification and correlations across all four markets.
Do not equate higher trade frequency with higher profitability.

## AI research process
- Provide the Fusion Council with versioned, reproducible evidence packets.
- Keep independent AI analyses separate before debate.
- Preserve contrary evidence and minority opinions.
- Require the deterministic Risk Engine to approve every proposed virtual trade.
- Never allow an AI-generated numerical claim to replace verified calculations.

## Forward paper trading
- Start only after infrastructure, data pipelines and implementation are ready.
- Run an initial 16-calendar-day forward paper-trading evaluation.
- Track orders, fills, fees, slippage, funding and portfolio equity.
- Compare live paper results against historical expectations and benchmarks.
- Treat 16 days as a preliminary evaluation, not proof of long-term profitability.
- Do not enable real-money execution automatically.

## Reporting
Produce reproducible reports with:
- Strategy and configuration versions.
- Data sources and evaluation periods.
- Gross and net performance.
- Risk-adjusted metrics and drawdowns.
- Benchmark comparisons.
- Failure cases, uncertainty and limitations.
- Recommendations for further testing.

## Security and status
Never store API keys or broker credentials in Git.
Use paper trading only during initial development and validation.
This skill is a specification, not an installed or functioning trading system.
