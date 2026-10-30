# BND master backlog — implementation status

Checked against `main` at `e3b5485` (30.10.2026). Status values:
**DONE** (implemented and tested), **PARTIAL** (some parts exist, listed
with evidence), **MISSING** (nothing usable yet), **BLOCKED** (needs a
decision, credential, budget or infrastructure from the owner).

Offline CI passing and synthetic backtests are not evidence of
profitability. No strategy has shown a statistically significant edge on
real data so far (runs 41057926902, 41061992492, 41063393336, 41068079079
on the `backtest-results` branch).

| # (issue) | Item | Status | Evidence in code | Remaining work |
|---|---|---|---|---|
| 1 ([#45](../../../issues/45)) | Five AI agents | PARTIAL · live round BLOCKED | `openrouter_adapter.py` (model per agent via `BND_MODEL_*`, timeout, strict JSON validation, reported model), `multi_ai_providers.readiness`, `scripts/overnight_five_agent_council.py` (five real calls, per-run and per-call USD caps, fail-closed), `cost_tracker.py`, `cost_storage.py` | Gateway LIVE mode (`ai_gateway.AIGateway.analyze` raises outside MOCK); bounded retry and failover; parallel calls; availability tracking; per-round and per-model budget in the gateway. A real five-agent round needs owner authorisation, model IDs (GPT-6 included) and a provider-side spend limit. |
| 2 ([#46](../../../issues/46)) | Fusion Council decision rules | PARTIAL | `fusion_council.FusionCouncil` (independent first votes, preserved revisions, strict majority, dissent, audit log), `debate_engine.DebateEngine` (arguments, challenges, responses, rounds), Risk veto in `trade_coordinator.coordinate_trade` | Weighted consensus, unanimity mode, performance-based weights, uncertainty → HOLD, a rule that a well-supported minority objection forces reconsideration before a decision. |
| 3 ([#47](../../../issues/47)) | AI → signal → virtual trade | PARTIAL | `trade_coordinator.coordinate_trade` (closed debate → majority → risk check → outcome), `risk_engine.evaluate_risk` | Structured signal (instrument, direction, entry, stop, take-profit), sizing, cost estimate, simulated order, portfolio update, full decision log. |
| 4 ([#48](../../../issues/48)) | Persistent paper-trading engine | MISSING | Backtesters simulate history only (`backtester.py`, `portfolio.py`); `cost_storage.py` shows the SQLite pattern | Persistent account, orders (market/limit), stops, take-profit, trailing stop, partial fills, rejections, costs, margin, history, idempotency, restart recovery, safe stop. |
| 5 ([#49](../../../issues/49)) | Advanced risk engine | PARTIAL | `risk_engine.py` (per-trade risk, daily loss and drawdown from day-start/peak, gross exposure, leverage), `portfolio.py` (volatility targeting on measured joint returns, gross leverage cap, kill switch in simulation), `backtester` gap fills | Per-instrument, sector and currency limits; liquidity; stale-data guard; persistent global kill switch; exposure reduction after losses; stress scenarios. |
| 6 ([#50](../../../issues/50)) | Multi-market historical data | PARTIAL | `market_data.py`: Binance OHLCV (crypto, intraday), Yahoo daily (forex, futures, indices, stocks) with quality report, gap detection, SHA-256 in reports | Intraday for non-crypto, spreads, exchange calendars, split/dividend adjustment, roll-adjusted futures, historical funding, incremental updates. |
| 7 ([#51](../../../issues/51)) | Walk-forward and out-of-sample | PARTIAL | `quant_evaluation`/`quant_report` (fixed-parameter folds), `backtest_cli run` (in/out-of-sample with warm-up), `robustness.py` (grid, in-sample selection, permutation test, cost stress), Holm correction in `compare` | Rolling/expanding re-optimisation per fold, purging/embargo, regime splits, parameter-stability report. |
| 8 ([#52](../../../issues/52)) | Strategies for every horizon | PARTIAL | `strategies.py`: SMA, EMA, MACD, ADX, Donchian, Keltner/ATR, momentum, RSI, Bollinger, Stochastic, volatility targeting; long/short; any Binance interval | Multi-indicator and AI-assisted strategies, per-asset-class adaptation, and statistical validation (none validated yet). |
| 9 ([#53](../../../issues/53)) | Dynamic strategy selection | MISSING | – | Regime detection, strategy weighting, degradation switch-off, controlled recalibration, comparison with static choice. |
| 10 ([#54](../../../issues/54)) | Profit and risk evaluation | PARTIAL | `backtester.compute_metrics` (return, CAGR, Sharpe, max drawdown, profit factor, win rate, fees), exposure metrics, per-market P&L in `portfolio.py`, benchmarks | Sortino, Calmar, expectancy, volatility, turnover, EUR base currency, per-strategy attribution. |
| 11 ([#55](../../../issues/55)) | Advanced multi-market portfolio | PARTIAL | `universe.py` (22 markets), `portfolio.py` (volatility sizing with correlations, leverage cap, per-market costs and carry, kill switch, warm-up, data diagnostics) | Individual stocks, allocation across strategies, concentration limits, FX translation to a base currency, margin and liquidation, multi-market stress tests, tradable-instrument mapping. |
| 12 ([#56](../../../issues/56)) | Multichain monitoring | MISSING · BLOCKED | – | Needs node or indexer access (e.g. RPC/websocket providers for Ethereum, Solana, Base, BNB Chain) and keys. |
| 13 ([#57](../../../issues/57)) | Smart-money wallets | MISSING · BLOCKED | – | Depends on 12. |
| 14 ([#58](../../../issues/58)) | Potential-insider category | MISSING · BLOCKED | – | Depends on 12–13; must stay explainable and avoid unjustified labels. |
| 15 ([#59](../../../issues/59)) | Crypto Radar paper trading | MISSING · BLOCKED | – | Depends on 4 and 12–14; initial virtual capital must be confirmed. |
| 16 ([#60](../../../issues/60)) | AI Management orchestrator | PARTIAL | `code_review_loop.py`, `review_budget.py`, overnight review workflows | Task distribution, decision registry, agent performance tracking, fallback, local AI. |
| 17 ([#61](../../../issues/61)) | iPhone notifications | MISSING · BLOCKED | – | Needs the channel choice (e.g. Pushover, ntfy, Telegram) and its credential. |
| 18 ([#62](../../../issues/62)) | Permanent operation and recovery | PARTIAL | Scheduled GitHub Actions, persistent results on `backtest-results` | Long-running service, health checks, backups, Proxmox migration path. Depends on 4. |
| 19 ([#63](../../../issues/63)) | AI cost management | PARTIAL | `cost_tracker.py`/`cost_storage.py` (daily/monthly budgets, reservations, reconciliation), overnight per-run/per-call caps, `review_budget.py` | Per-model budgets, cache, model choice by task, cost report, separate development and research budgets. |
| 20 ([#64](../../../issues/64)) | Security and compliance | PARTIAL | Secrets only via Actions secrets, `permissions: contents: read` (write only in isolated publish jobs), paid-AI flags, `tests/test_workflow_flags.py`, actionlint + shellcheck in CI | Central MOCK/PAPER/LIVE mode guard, audit log, dependency audit, automated security scanning. |
| 21 ([#65](../../../issues/65)) | 16-day paper-forward evaluation | MISSING · BLOCKED | – | Starts only after 1–5 are accepted; needs frozen configuration and confirmed virtual capital. |
| 22 ([#66](../../../issues/66)) | Independent final audit | PARTIAL | 560 unit tests, reference-implementation tests for indicators, `docs/CLAUDE_AUDIT_REPORT_2026-10-30.md`, CI lint | Integration, end-to-end, restart, concurrency and extreme-risk tests for the paper engine; GPT-6 cross-audit. |

## Order of work (phase A first)

1. #2 Fusion Council decision rules — no dependencies.
2. #10 missing metrics — no dependencies.
3. #4 persistent paper-trading engine, with #5 controls it needs (persistent kill switch, per-instrument limits, stale data).
4. #3 signal → virtual trade pipeline on top of #4 and #2.
5. #1 gateway LIVE path (retry, failover, parallel, budgets) tested in MOCK; the live round itself waits for authorisation.

The BND Command Center Dashboard belongs to GPT-6; Claude provides data
and API contracts only.
