# BND-Global-Trading-Intelligence

Multi-agent AI research and paper-trading infrastructure. No live orders
are ever placed.

## What exists today

| Module | Purpose |
| --- | --- |
| `fusion_council` | Five independent agent votes (GPT, Claude, Gemini, Grok, DeepSeek), revisions, strict-majority decision, audit log |
| `debate_engine` | Structured debate rounds; every agent must argue and respond before closing |
| `risk_engine` | Deterministic veto: leverage, daily loss, drawdown, exposure and per-trade risk limits |
| `trade_coordinator` | Combines a closed debate with risk checks into a paper-trade outcome |
| `ai_gateway` | Provider routing with budget reservations (MOCK mode only) |
| `openrouter_adapter` | Opt-in OpenRouter client returning validated BUY/SELL/HOLD analyses |
| `cost_tracker`, `cost_storage` | In-memory and SQLite token-cost accounting with daily/monthly budgets |
| `market_data` | Validated OHLCV candles, CSV storage, Binance (crypto) and Yahoo Finance (forex, futures, indices, stocks) downloads with data-quality reports |
| `backtester` | Next-open execution, fees, slippage, stop losses, risk-engine sizing, metrics |
| `strategies` | Trend (SMA, EMA, MACD, ADX), breakout (Donchian, Keltner/ATR), momentum, mean reversion (RSI, Bollinger, Stochastic), volatility targeting |
| `universe`, `portfolio` | 22 markets (forex, commodities, indices, bonds, crypto) traded in one leveraged account with volatility sizing and a drawdown kill switch |
| `quant_backtest`, `quant_evaluation`, `quant_metrics`, `quant_report` | Long/flat SMA walk-forward folds with risk-adjusted metrics versus buy-and-hold |
| `council_orchestrator`, `council_round`, `live_council_bridge` | Five-agent research rounds; the paid live council stays disabled |
| `code_review_loop`, `review_budget`, `manual_live_review` | GPT → Claude → GPT review with a fail-closed USD 0.50 preflight |
| `ai_smoke_test`, `three_agents_live` | Manual, confirmed single-call connectivity checks |

`market_data.Candle` is the canonical data format; `market_data.to_bars`
adapts it for the `quant_*` modules.

Not yet implemented: walk-forward optimisation, AI-agent strategies in
backtests, and LIVE gateway mode.

## Quick start

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python -m src.bnd.paper_demo
```

The demo runs the full council → debate → risk → trade pipeline offline
with mock agents.

## Backtesting

```bash
python -m src.bnd.backtest_cli fetch --symbol BTCUSDT --interval 4h \
    --start 2019-01-01 --out data/BTCUSDT-4h.csv
python -m src.bnd.backtest_cli run --data data/BTCUSDT-4h.csv \
    --strategy sma_crossover --stop-loss 5 --risk-per-trade 1
python -m src.bnd.backtest_cli walk-forward --data data/BTCUSDT-4h.csv \
    --window 50 --train 1000 --test 500
python -m src.bnd.backtest_cli robustness --data data/BTCUSDT-4h.csv \
    --strategy sma_crossover --stop-loss 5 --risk-per-trade 1
```

Strategies return a target exposure in [-1, 1]; fractions such as 0.6
hold 60% of the allocation, and positions are resized only when the
target moves by `--rebalance` points (default 10).

`volatility_target` holds `--target-vol` / realised volatility (capped at
100%, no leverage), optionally flat below a `--trend` SMA. It aims at a
better risk-adjusted result, not at beating buy-and-hold on return, so
judge it by out-of-sample Sharpe and drawdown. A protective stop blocks
re-entry until the target turns flat, which without `--trend` may never
happen; research runs therefore use `--no-risk-gate --trend 1200`.
`--long-short` goes short (same volatility sizing) while the close is
below the trend average.

Carry costs: `--funding` charges an annual percentage on open position
notional, long or short (perpetual funding or borrow; default 10 when
shorts are allowed, 0 for spot long-only). `--cash-rate` pays annual
interest on uninvested equity (default 0). Buy-and-hold is treated as a
spot holding without funding.

Strategy parameters: `--param name=value` (repeatable), e.g.
`--strategy rsi_reversion --param period=21 --param oversold=25`. Add
`--allow-short` to let any strategy take its short signals.

`compare` runs every strategy with default parameters and ranks them on
out-of-sample Sharpe. Each has a permutation test; `p_value_adjusted`
(Holm) corrects for testing them all at once, since one of eight
strategies looking lucky at p < 0.05 is likely even on random data.
The workflow's default strategy `all` runs this comparison.

`robustness` asks whether a result is an edge or luck:
- **Parameter grid:** every combination (`--fast-range 10:50:10 --slow-range 50:200:25`);
  a lone good setting among poor neighbours is overfitting.
- **In-sample selection:** parameters are chosen on the first 70% only, then
  ranked on the unseen 30%.
- **Permutation test:** the same positions and holding periods, shuffled in
  time 200 times. A `p_value` above 0.05 means the timing is indistinguishable
  from luck.
- **Cost stress:** fees and slippage ×1, ×2, ×3.

Reports include the dataset SHA-256 and exposure (`time_in_market_pct`,
`avg_capital_exposure_pct`): beating buy-and-hold in a falling market with
little capital invested is not evidence of an edge.

Decisions use only past candles and fill at the next open, paying fees
and slippage (defaults: 0.10% and 0.05% per fill). Each report compares
the strategy with buy-and-hold for the full, in-sample (first 70%) and
out-of-sample periods. Judge a strategy by its out-of-sample results.
The "BND Backtest (manual)" workflow runs the same steps on GitHub, shows
a summary with a conservative verdict on the run page
(`src/bnd/backtest_summary.py`), and saves the JSON reports to the
`backtest-results` branch under `runs/<time>_<run id>_<symbol>_<interval>_<strategy>/`
(`LATEST.md` holds the newest summary). Only the separate `publish` job has
write access; it never runs project code and only writes that branch.

## Multi-market portfolio

```bash
python -m src.bnd.backtest_cli fetch-universe --start 2010-01-01 --out-dir data/universe
python -m src.bnd.backtest_cli portfolio --data-dir data/universe --strategy all \
    --max-leverage 3 --portfolio-vol 15
```

Every market gets the strategy's signal, sized at
`signal × portfolio_vol / market vol`, so calm markets (forex) hold more
notional than volatile ones. The whole book is then scaled so that its
volatility, measured on the last `--sizing-lookback` dates of real joint
returns (correlations included), equals `--portfolio-vol`. Gross exposure
is capped at `--max-leverage`. Per-market fees, slippage and carry depend
on the asset class (`universe.CLASS_COSTS`): crypto perpetuals pay about
10%/yr funding, futures pay no financing on notional. `--financing` adds
an optional cost on exposure above equity (margin loans, CFDs; default 0).
Reports list each market's largest daily move to expose bad data. The
kill switch (`--max-drawdown`, default 30%) closes everything and stops
trading. Reports compare each strategy with an equal-weight long basket
(1x), sweep leverage (1x, 2x, 3x, 5x) and stress costs. Caveats: Yahoo
futures (`=F`) are not roll-adjusted, indices stand in for futures/CFDs,
and there is no permutation test for portfolios yet. The "BND
Multi-Market Portfolio (manual)" workflow runs this on GitHub.

Leverage in single-market runs: `--leverage 3` (risk-engine cap
`--max-leverage`). Losses scale with leverage; an account can be wiped out.

## Paper-trading engine

`paper_engine.PaperEngine` keeps a virtual account in one SQLite file
(`PaperEngine.create(path, capital)` once, `PaperEngine.open(path)` after a
restart). Every bar (`on_bar`) and order (`submit_order`) is one
transaction. Orders: market or limit, stop-loss, take-profit, trailing
stop, reduce-only, partial fills capped by bar volume, expiry. The client
order id makes resubmission idempotent. Mandatory checks on every opening
order, at submission and again at fill: kill switch, known instrument,
fresh data, no extreme gap, protective stop, per-instrument and per-sector
exposure, risk per trade, daily loss, drawdown and gross leverage. The
kill switch (daily loss, drawdown or margin below maintenance) closes
everything, survives restarts and needs `reset_kill_switch("RESET-KILL-SWITCH")`.
An unexpected error rolls the bar back and trips it. `TradingMode.LIVE`
is refused: no real orders exist in this system.

## Paid API calls

All OpenRouter calls are opt-in. The workflows under `.github/workflows`
that call paid models require manual dispatch with explicit confirmation
inputs, and an `OPENROUTER_API_KEY` secret with a provider-side spending limit.

Safety flags read by the code: `BND_ALLOW_LIVE_AI` (live provider adapters)
and `BND_ALLOW_PAID_AI` (overnight scripts). Both default to off.
`tests/test_workflow_flags.py` fails if a workflow sets a `BND_*` variable
that no code reads.
