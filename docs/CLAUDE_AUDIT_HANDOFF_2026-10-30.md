# Claude audit handoff — 30 October 2026

## Reproducible refs
- Main after PR #41: `b72b951f75706ca660974a82ea4e23a0eaa1ce59`.
- Claude's independent hardening branch at review: `fix/core-hardening`, commit `324608b13f9cc90b39f1047e489a3f0513a27480`.
- Latest observed Python CI on that Claude commit: run `41028770568`, successful. This does not mean all safety requirements have passed.
- **Do not fast-forward, reset or edit Claude's branch.** Review on a new integration branch; re-run tests after reconciliation.

## What is actually available on main
- Offline five-agent regression tests, cost and fail-closed checks (#34).
- Long-only next-bar open backtester, independent SMA forward folds, buy-and-hold benchmark (#35–#37).
- Net return, annualized Sharpe, CAGR, maximum drawdown and aligned benchmark comparison (#38).
- Audit checklist (#39), per-fold risk-adjusted report (#40), UTC chronological CSV validation (#41).
- No historical multi-market performance result has been validated. No live trading or 16-day forward test has started.

## What exists only on Claude's branch
- `market_data.py`: timezone-aware OHLCV Candle validation and public Binance data retrieval.
- `backtester.py`: long/short simulation, stop handling, costs, risk checks and performance metrics.
- `strategies.py`, `backtest_cli.py`: strategy factories and a backtest command line.
- `paper_demo.py`: mock council/debate/risk demonstration, not a connected broker or production paper broker.
- Associated tests and `.github/workflows/backtest.yml`.

## Prioritized review findings — investigate before any paper-forward launch

### BLOCKER CANDIDATE A: Risk gate is optional in backtester CLI
- Evidence: `src/bnd/backtest_cli.py` initializes `risk_limits = None` and creates limits only if `--risk-per-trade` is supplied; `src/bnd/backtester.py` invokes `evaluate_risk` only when `config.risk_limits is not None`.
- Consequence: a default backtest may open positions without the claimed hard risk veto. This may be acceptable for a clearly labeled research baseline, **not** for a paper-forward executor.
- Acceptance test: launch a paper-only trade proposal with risk limits omitted; assert fail-closed rejection or an explicit research-only mode. Verify risk veto always overrides AI consensus in the actual paper coordinator.

### BLOCKER CANDIDATE B: Overnight gaps and daily loss accounting
- Evidence: `_Simulator.start_bar` resets `day_start_equity` to `equity(candle.open)` at the first candle of each new date, before entry decisions. `open_position` then computes daily loss relative to this reset value.
- Risk: a losing overnight gap may not count toward the next day's daily-loss cap. Verify expected policy for calendar-day versus session-day P&L.
- Acceptance test: hold a long across midnight, gap down at next open, then attempt a new entry; assert daily loss and drawdown caps account for the gap under the documented policy.

### REVIEW C: Out-of-sample strategy warm-up
- Evidence: `backtest_cli.py` splits data and calls `run_backtest(period, _make_strategy(args), config)` separately for each period; no training history is passed to the out-of-sample strategy.
- Risk: indicator warm-up at the beginning of the test interval can suppress valid signals. This is not future-data leakage, but changes the measured forward performance.
- Acceptance test: allow strategy warm-up from training candles without counting training P&L; compare with independent test-start baseline.

### REVIEW D: Data and metrics parity
- Claude's `Candle` is OHLCV and timezone-aware; main's `Bar` is open/close only. Define a canonical data contract before merging two backtest paths.
- Check fee, slippage, stop fill, forced final liquidation and equity-curve conventions; they differ between modules.
- Validate missing intervals, volume, exchange-specific fees, funding, FX conversion, delisted assets and corporate actions before any cross-market performance claim.
- Use realistic historical and untouched out-of-sample data; CI passing on synthetic fixtures is insufficient.

## Audit outputs required
For each finding, provide severity, file/line, a minimal reproducible case, patch proposal, regression test, original/revised AI votes where relevant, and an explicit paper-forward blocking decision. Keep unverified claims marked as hypotheses.

## Reproduce safely
```bash
git fetch origin
git switch main
git pull --ff-only
python -m pip install -r requirements.txt
python -m pytest -q
git diff --stat origin/main...origin/fix/core-hardening
```

Do not run live OpenRouter smoke tests or paid AI workflows without explicit authorization and verified budgets. Do not connect real broker credentials. The 16-day evaluation begins only after the audited paper-only pipeline passes its acceptance gates.
