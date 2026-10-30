# Claude audit report — 30 October 2026

Branch: `integration/claude-audit-20261030` = `main` (a517533, PR #44)
merged with `fix/core-hardening` (324608b, unchanged), plus the fixes below.
Offline suite: 402 tests pass. No paid AI calls, live data or broker
connections were used. All results are on synthetic fixtures; no
historical performance claim is made.

## Handoff findings

### A. Risk gate optional in backtester CLI — HIGH, fixed
- Files: `src/bnd/backtest_cli.py` (`command_run`), `src/bnd/backtester.py` (`run_backtest` metrics).
- Reproduction: `backtest_cli run --data X.csv` ran without any risk veto.
- Fix: the CLI now fails closed. It requires `--risk-per-trade` with `--stop-loss`, or an explicit `--no-risk-gate`. Every report carries `risk_gate: enforced | disabled_research_only`.
- Tests: `test_cli_refuses_to_run_without_risk_gate`, `test_cli_research_mode_is_labelled`, `test_metrics_label_risk_gate`.
- The paper coordinator already fails closed on missing limits (#44, `tests/test_paper_risk_gate.py`).
- Paper-forward blocking: no longer blocking. The backtester is a research tool and does not route paper orders.

### B. Overnight gap excluded from daily loss — HIGH, fixed
- File: `src/bnd/backtester.py`, `_Simulator.start_bar`.
- Reproduction: hold a long into 00:00 UTC; the first candle gaps 50% down. Before the fix, `day_start_equity` was reset to equity *after* the gap, so the next entry saw 0 daily loss.
- Policy (documented in code): UTC calendar day, measured from the previous day's final close mark.
- Test: `test_overnight_gap_counts_toward_next_day_loss_limit`. It fails before the fix and passes after.
- Paper-forward blocking: would have blocked; resolved.

### C. Out-of-sample warm-up — MEDIUM, fixed
- File: `src/bnd/backtest_cli.py`; new `trade_from` argument in `run_backtest`.
- Before: the out-of-sample run started cold, so SMA/Donchian could not signal for the first `slow`/`entry` bars.
- Fix: the out-of-sample run passes all candles with `trade_from = split`. Strategies see in-sample history; nothing before the split is traded or counted. The decision on the last in-sample close executes at the first out-of-sample open, the same convention as `quant_evaluation.evaluate_sma_walk_forward`.
- Tests: `test_warm_up_candles_are_seen_but_not_traded`, `test_cli_out_of_sample_starts_at_split_with_warm_up`.
- Paper-forward blocking: no.

### D. Data and metrics parity — MEDIUM, partially resolved
- Fill, fee and slippage conventions verified identical between `quant_backtest.backtest` and `backtester.run_backtest` for long/flat signals (`test_parity_with_main_quant_backtester`). The single documented difference: `backtester` liquidates at the final close (paying exit costs), while `quant_backtest` marks open units at the final close.
- Sharpe now accepts a risk-free rate, matching `quant_metrics` (`test_sharpe_subtracts_risk_free_rate`).
- Gap detection added (`market_data.find_gaps`); reports list gaps and `--require-continuous` rejects them (`test_find_gaps_reports_missing_candles`, `test_cli_require_continuous_rejects_gaps`). This suits 24/7 markets only.
- **Open:** choose one canonical data contract. Proposal: `market_data.Candle` (OHLCV, timezone-aware) as canonical, with `Bar(c.open, c.close)` as the adapter for the `quant_*` walk-forward path. Not done here, to avoid changing merged APIs without agreement.
- Paper-forward blocking: not for a single crypto market. Blocking for any cross-market claim (funding, FX, sessions, corporate actions are unmodelled).

## Additional findings

### E. Overnight AI review made unapproved paid calls — HIGH, fixed
- Files: `.github/workflows/bnd-overnight-ai-review.yml`, `scripts/overnight_ai_review.py`.
- Before: the nightly schedule called OpenRouter whenever a key existed, contrary to the documented "paid calls require explicit authorization". Failures still exited 0. Only the first 12 source files were sent.
- Fix: calls require repository variable `BND_ALLOW_PAID_AI=true` (default off); failures exit 1; all files are included within a 48k-character budget, with omissions listed.
- Tests: `tests/test_overnight_ai_review.py`.

### F. Non-positive equity could crash the next entry — LOW, fixed
- File: `src/bnd/backtester.py`, `open_position`. A short gapping through its stop can push equity to zero or below; `Portfolio` then raised `ValueError`. Entries are now rejected instead.
- Test: `test_wiped_out_account_rejects_entry_instead_of_crashing`.

### Reviewed without changes
- `quant_backtest`, `quant_evaluation`, `quant_metrics`, `quant_report` (main): next-open execution, warm-up handling, fold independence and metric edge cases behave as documented.
- `trade_coordinator` fail-closed checks (#44) merge cleanly with the debate/council validation changes from `fix/core-hardening`.

## Known limitations (hypotheses, not verified)
- Donchian strategy tracks its own position; after a stop-out the backtester blocks re-entry until the strategy's own exit fires. Behaviour is consistent, but the strategy's internal state can differ from the account.
- Intrabar stop ordering is unknown on OHLC data; stops fill at the stop (or worse open), which is conservative only when price did not reach the target first.
- Feature flags are named inconsistently: `BND_ALLOW_LIVE`, `BND_ALLOW_LIVE_AI`, `BND_ALLOW_PAID_AI`.
- No real historical dataset has been backtested from this environment (Binance is blocked by the session network policy).

## Paper-forward decision
Not ready. Remaining gates: the canonical data contract (D), a real historical out-of-sample run with recorded dataset hash, and connecting council decisions to paper proposals with the risk veto.
