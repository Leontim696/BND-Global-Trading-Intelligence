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
| `ai_gateway`, `council_runner` | Provider routing with budget reservations; parallel five-agent rounds with retries, failover and per-round budgets; LIVE only with explicit authorisation |
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

Also: `decision_rules` (majority, weighted, unanimity, HOLD on
uncertainty), `paper_engine` (persistent virtual account), `signal_pipeline`
(council decision → virtual order), `walk_forward` (re-optimisation).
Not yet implemented: AI-agent strategies in backtests and a real five-agent
paid round (needs authorisation).

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
python -m src.bnd.backtest_cli walk-forward-opt --data data/BTCUSDT-4h.csv \
    --strategy sma_crossover --no-risk-gate --train 1000 --test 250 --mode rolling
```

`walk-forward-opt` re-chooses parameters on each training window only and
trades the next window after an `--embargo`; test windows are chained
into one out-of-sample record. It reports parameter stability and the
gap between train and test Sharpe (overfitting), and compares the record
with and without switching the strategy off after poor recent folds.

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
Reports list each market's largest daily move to expose bad data.
`--universe etf` trades tradable ETFs (GLD, USO, SPY, IEF, ...) instead of
raw futures and indices: no artificial roll jumps, prices adjusted for
dividends and splits. Each strategy gets a portfolio permutation test
(`--permutations`, default 40): every market's signal timing is shuffled
while positions, holding periods, sizing and leverage stay the same.
Holm-adjusted p-values correct for comparing all strategies. An
always-long strategy has nothing to shuffle and gets p = 1: its result
is diversification and leverage, not timing. The
kill switch (`--max-drawdown`, default 30%) closes everything and stops
trading. Reports compare each strategy with an equal-weight long basket
(1x), sweep leverage (1x, 2x, 3x, 5x) and stress costs. Caveats: Yahoo
futures (`=F`) are not roll-adjusted, indices stand in for futures/CFDs,
and portfolio p-values compare strategies on one dataset only. The "BND
Multi-Market Portfolio (manual)" workflow runs this on GitHub.

Leverage in single-market runs: `--leverage 3` (risk-engine cap
`--max-leverage`). Losses scale with leverage; an account can be wiped out.

Prices are in USD. `--base-currency EUR` (default in `portfolio.yml`) also
reports every strategy and the basket as a EUR investor sees them,
unhedged: the USD equity curve is converted at each date's EURUSD close,
so a falling dollar lowers the result. It needs `EURUSD.csv` (forex class).

`--strategy combo` trades the equal-weight average of several strategies'
signals (`--members`, default `regime_switch,momentum,bollinger_reversion`:
trend following plus mean reversion). The report shows, for each member,
its result alone and the combo's result without it, so a member that adds
nothing is visible. The paper runner accepts the same `--strategy combo
--members ...`.

`--strategy selector` chooses per market: every member runs all the time,
and every `hold` candles (default 21) the one with the best recent Sharpe
(own paper returns over `lookback` candles, default 252, no costs) is
followed; if none scored above `min_score` (default 0) the market stays
flat until the next choice. Members default to `regime_switch, momentum,
sma_crossover, donchian_breakout, bollinger_reversion, rsi_reversion`.

`--strategy cross_momentum` ranks markets against each other: each day
every market is scored by its return over `lookback` candles (default
252) skipping the last `skip` (21); the top `fraction` (1/3) is long, the
bottom short, the rest flat. The ranking for a date uses only candles of
earlier dates, because markets close at different hours. Also in the
paper runner and in `--strategy all`.

`portfolio-wfo` is walk-forward for the whole book: in calendar windows
(default 4 years of training, 1 year of testing, 5 days embargo) the
parameter set with the best training Sharpe is chosen and then traded on
the next unseen year, each window from fresh equity and compared with the
equal-weight basket on the same dates. In `portfolio.yml` choose
`mode: walk-forward`.
`--strategy buy_and_hold` runs the same walk-forward always long, with the
same volatility sizing and leverage: the control that separates a
strategy's timing from what sizing and leverage alone earn. On ETFs,
leverage means a margin loan: with `--universe etf` the portfolio commands
charge 5%/yr on exposure above equity by default (`--financing` overrides;
futures default to 0 because their financing is in the price).
`--per-class` chooses a parameter set for each asset class separately,
each on the training window of that class's markets alone.

## Paper-trading engine

`paper_engine.PaperEngine` keeps a virtual account in one SQLite file
(`PaperEngine.create(path, capital)` once, `PaperEngine.open(path)` after a
restart). Every bar (`on_bar`) and order (`submit_order`) is one
transaction. Orders: market or limit, stop-loss, take-profit, trailing
stop, reduce-only, partial fills capped by bar volume, expiry. The client
order id makes resubmission idempotent. Mandatory checks on every opening
order, at submission and again at fill: kill switch, known instrument,
fresh data, no extreme gap, protective stop, per-instrument and per-sector
exposure, net exposure per currency (forex pairs count on both sides,
so long EURUSD is long EUR and short USD), the whole book's volatility
from recent joint returns (`max_portfolio_vol_pct`, default 40%/yr, so
markets that move together count together; hedges are always allowed),
broker margin per market (`Instrument.margin_pct`; the paper runner uses
the ESMA retail CFD minimums from `universe.esma_margin_pct`: major forex
3.33%, gold and major indices 5%, other commodities and indices 10%,
bonds 20%, crypto 50%) with a close-out when equity falls below half the
required margin, risk per trade, daily loss, drawdown and gross leverage. The
kill switch (daily loss, drawdown or margin below maintenance) closes
everything (at today's price where it is known, otherwise with a
reduce-only order at that market's next open, so a gap is not skipped),
survives restarts and needs `reset_kill_switch("RESET-KILL-SWITCH")`.
An unexpected error rolls the bar back and trips it. `TradingMode.LIVE`
is refused: no real orders exist in this system.

### Daily paper runner

`paper_runner` is one daily step of a virtual multi-market account:
new closed candles are fed to the engine (yesterday's orders fill at the
new opens), the strategy is replayed and sized exactly like the portfolio
backtest (`portfolio.target_weights`), the weights are fitted inside the
engine's position, sector, leverage and risk-at-stop limits, and the
differences become orders for the next open. Reductions are reduce-only;
added risk carries a stop `--stop-atr` x ATR away. Client order ids are
`<candle date>:<market>`, so a repeated run submits nothing new.

```bash
python -m src.bnd.backtest_cli fetch-universe --universe etf --start 2023-01-01 --out-dir data
python -m src.bnd.paper_runner --state paper.sqlite --data-dir data --capital 10000 \
    --strategy regime_switch --report REPORT.md
```

`--capital` is required once and refused afterwards. Trading settings are
stored in the account at creation and reused by every later run; a run
with different settings is refused. The `paper-trading.yml` workflow runs
this every day at 22:23 UTC (candles cached between runs and updated with
`fetch-universe --update`, which re-downloads a market in full when Yahoo
has re-adjusted its history) and keeps the account and its status page
(`README.md`) on the `paper-trading` branch. Until a manual run creates
the account with a virtual capital, scheduled runs do nothing.

Each status page also shows `scenarios.py` stress tests: what the current
positions would lose in an instant repeat of 2008, the 2020 crash, 2022
rates, a one-day crash, a dollar spike or a crypto collapse (stylised,
rounded moves per market and asset class), and whether that would trip
the kill switch.

## Decision registry

`decision_registry.DecisionRegistry` stores every council decision with
each agent's initial and final vote and confidence, the price and a
horizon (default 5 days). `settle_from_candles` settles due decisions
with the first close at or after the horizon; `scorebook()` turns the
outcomes into an `AgentScorebook` (weights for the weighted rule) and
`performance()` reports each agent's hit rate and Brier score and the
council's own hit rate.

## Safety

`safety.trading_mode()` is the single mode check: `BND_TRADING_MODE` may be
MOCK or PAPER (default); LIVE or anything else is refused, so no setting
can switch on real orders. `tests/test_safety.py` also scans `src`,
`scripts` and the workflows for broker/exchange order endpoints and for
leaked keys. CI runs Bandit (`-ll`); reviewed exceptions are marked
`# nosec <id>` with the reason on the line above. Dependabot proposes
weekly updates for Actions and the test dependency.

## Paid API calls

`ai_cache.ResponseCache` (pass `cache=` to `CouncilRunner`) stores each
answer under a SHA-256 of agent, model, market, symbol and context for 12
hours, so an identical question is never paid for twice; hits and money
saved are counted. `python -m src.bnd.cost_report --db costs.sqlite
[--cache cache.sqlite]` prints spending by model, agent and day.

`ai_budgets.BudgetSet` keeps a separate cost file and daily/monthly limit
for research, development and trading, so one purpose cannot spend
another's money; a purpose without a budget cannot spend at all.
`choose_model(task, options)` picks the cheapest configured model that
reaches the task's minimum tier (trading votes always need the top tier).

All OpenRouter calls are opt-in. The workflows under `.github/workflows`
that call paid models require manual dispatch with explicit confirmation
inputs, and an `OPENROUTER_API_KEY` secret with a provider-side spending limit.

Safety flags read by the code: `BND_ALLOW_LIVE_AI` (live provider adapters)
and `BND_ALLOW_PAID_AI` (overnight scripts). Both default to off.
`tests/test_workflow_flags.py` fails if a workflow sets a `BND_*` variable
that no code reads.
