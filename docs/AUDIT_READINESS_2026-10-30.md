# BND Audit Readiness — 30 October 2026

## Scope and current evidence
- Main contains merged PRs #34–#38: five-agent offline regression tests, next-open long-only backtester, CSV/SMA walk-forward evaluation, boundary tests, and performance metrics.
- The five-agent council workflow previously completed successfully (run 41022745570), with five reported responses. This is a code-review council test, **not** proof of trading strategy profitability.
- Keep Claude's `fix/core-hardening` branch separate until its changes have been reviewed against current main; do not overwrite its validation improvements.
- Offline Python CI passing does not establish correctness of historical market data, profitability, provider-side billing limits, or production readiness.

## Audit gates (all must pass before starting the 16-day paper-forward evaluation)
1. **Branch reconciliation:** review every changed file on `fix/core-hardening` against main, resolve conflicts, and require CI on the integration PR.
2. **Council correctness:** verify independent first votes, dissent evidence, revised votes and reasons, vote snapshots, majority/unanimity rules, missing/invalid responses and fail-closed handling. Confirm real provider adapters match the orchestrator interface.
3. **Trading safety:** prove no live order routing is reachable; risk veto must override AI consensus. Test loss caps, drawdown, gross exposure, leverage, stop assumptions, and negative/NaN inputs.
4. **Data provenance:** choose licensed/reliable historical feeds per market; validate timestamp timezone, missing/duplicate candles, corporate actions, funding, splits, delistings, liquidity and survivorship bias. The current CSV reader expects lexicographically sortable ISO timestamps.
5. **Backtesting integrity:** verify next-bar execution, gaps, realistic slippage, spread, commissions, funding, short borrow costs, position sizing and cash accounting. Current backtester is **long-only**, uses fractional units and marks open positions at the final close; it is not a complete multi-asset execution simulator.
6. **Walk-forward integrity:** use fixed train/test windows, purged/embargoed folds if labels overlap, no leakage in feature selection, separate parameter selection from final holdout, and test costs under stress.
7. **Performance evaluation:** compare absolute net return and risk-adjusted performance (Sharpe, drawdown, CAGR) against buy-and-hold and a no-trade baseline. Document sampling frequency and small-sample limitations.
8. **Operations:** capture reproducible commit SHA, Python version, test logs, dataset hashes, configuration, secrets isolation, alerts and recovery procedures. Paid AI calls require explicit authorization and budget controls.
9. **Paper-forward launch:** only after audit acceptance, freeze a version and run 16 calendar days paper-only with daily P&L, exposure, fills, rejected orders, costs and AI dissent logs.

## Outstanding work — not claimed complete
- Connect verified historical data and implement market-specific instruments (crypto, FX, equities, commodities).
- Implement/test long-short positions, portfolio allocation, risk-aware execution and simulated fills.
- Connect five-agent analysis to paper-trade proposals with hard risk veto and replayable audit logs.
- Validate real provider integrations and cost caps separately from offline mocks.
- Establish a dashboard/iPhone alert path and multichain wallet-monitoring pipeline.
- Run actual out-of-sample backtests and the subsequent 16-day forward test; no profitability claim is warranted yet.

## Claude review checklist
Ask Claude to provide: severity, file/line, reproducible failure, minimal patch, regression test, and whether each issue blocks paper-forward launch. Preserve dissent and avoid merging untested fixes. Record accepted/rejected findings with reasons.

## Safe immediate workflow
```bash
git fetch origin
git switch main
git pull --ff-only
python -m pip install -r requirements.txt
python -m pytest -q
git diff --stat main...origin/fix/core-hardening
```
The diff command is for review only. Create a new integration branch for accepted fixes and re-run CI; do not merge Claude's branch blindly.
