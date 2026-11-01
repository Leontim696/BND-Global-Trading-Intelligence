"""Daily virtual trading: strategy -> portfolio weights -> paper orders.

Run once a day after the closes. Each run:

1. Feeds every closed candle the account has not seen yet into the paper
   engine, in time order. Orders from the previous run fill at the first
   new open; stops, carry, marks and the kill switch are applied there.
   A new account only takes the latest candle: history is never traded.
2. Replays the strategy over each market's history and sizes the book
   exactly as the portfolio backtest does (``portfolio.target_weights``:
   volatility sizing with measured correlations, weight and leverage caps).
3. Fits the weights inside the engine's own limits (position, sector,
   gross leverage, risk at the stop) and submits the difference as orders
   for the next open. Reductions are reduce-only; anything that adds risk
   carries a protective stop ``stop_atr`` x ATR away.

Client order ids are ``<candle date>:<market>``, so running twice on the
same data submits nothing new. Virtual money only: the engine refuses
LIVE. Differences from the backtest, stated rather than hidden: the
engine's stops and limits can close or shrink positions the backtest
would hold, and markets are fed one by one.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from math import log
from pathlib import Path

from . import audit_log
from .backtest_cli import _factory, _pairs, _split_list
from .cross_sectional import cross_momentum_factory
from .market_data import MarketDataError, load_csv
from .paper_engine import (
    EngineLimits,
    Instrument,
    OrderRequest,
    PaperEngine,
    PaperEngineError,
)
from .portfolio import (
    PortfolioConfig,
    _Book,
    _History,
    _volatility,
    strategy_for,
    target_weights,
)
from .robustness import parse_value
from .safety import SafetyError, trading_mode
from .scenarios import run_scenarios
from .signal_pipeline import average_true_range
from .strategies import SWEEP_RANGES
from .universe import esma_margin_pct
from .universe import select as select_markets

REDUCED = re.compile(r"allows at most ([0-9.]+) notional")


@dataclass(frozen=True)
class RunnerConfig:
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    stop_atr: float = 3.0
    atr_period: int = 14
    # Stay this fraction inside every engine limit, so rounding and
    # moving prices do not turn a planned order into a rejection.
    margin: float = 0.98

    def __post_init__(self):
        if not self.stop_atr > 0 or self.atr_period < 2 or not 0 < self.margin <= 1:
            raise ValueError("stop_atr > 0, atr_period >= 2 and margin in (0, 1] required")


def instrument_for(market) -> Instrument:
    return Instrument(symbol=market.name, asset_class=market.asset_class,
                      fee_pct=market.fee_pct, slippage_pct=market.slippage_pct,
                      carry_pct_annual=market.carry_pct_annual,
                      sector=market.sector,
                      currency_pair=market.name if _is_pair(market) else "",
                      margin_pct=esma_margin_pct(market))


def _is_pair(market) -> bool:
    name = market.name
    return market.asset_class == "forex" and len(name) == 6 and name.isalpha() and name.isupper()


def feed_new_candles(engine: PaperEngine, data: dict) -> int:
    """Give the engine every candle newer than its marks, oldest first."""
    pending = []
    for name, candles in data.items():
        mark = engine.mark(name)
        if mark is None:
            pending.append((candles[-1].open_time, name, candles[-1]))
            continue
        seen = datetime.fromisoformat(mark["time"])
        pending.extend((c.open_time, name, c) for c in candles if c.open_time > seen)
    pending.sort(key=lambda item: (item[0], item[1]))
    for _, name, candle in pending:
        engine.on_bar(name, candle)
    return len(pending)


AI_WEIGHT = 0.5      # în strategia hibridă: jumătate regulile, jumătate consiliul AI


def latest_weights(data: dict, markets, factory, config: PortfolioConfig,
                   given_signals: dict | None = None, blend: bool = False) -> tuple[dict, dict]:
    """Today's portfolio weights and raw signals, as the backtest computes them."""
    books, signals = [], {}
    for market in markets:
        candles = data[market.name]
        if given_signals is not None and not blend:
            # Semnale venite din afară (consiliul AI); o piață fără semnal nu are poziție nouă.
            strategy, signal = (lambda history: 0.0), float(given_signals.get(market.name, 0.0))
        else:
            strategy = strategy_for(factory, market)
            signal = 0.0
            for end in range(1, len(candles) + 1):
                signal = strategy(_History(candles, end))
            if blend and market.name in (given_signals or {}):
                # Hibrid: regulile și consiliul se amestecă; la dezacord se anulează, la acord crește.
                signal = (1 - AI_WEIGHT) * signal + AI_WEIGHT * float(given_signals[market.name])
        signal = signal if (signal >= 0 or config.allow_short) else 0.0
        book = _Book(market, candles, strategy, signal=signal,
                     vol=_volatility(candles, len(candles), config.vol_lookback))
        book.returns = {b.open_time: log(b.close / a.close)
                        for a, b in zip(candles, candles[1:])}
        books.append(book)
        signals[market.name] = signal
    times = sorted({c.open_time for candles in data.values() for c in candles})
    return target_weights(books, config, times[-config.vol_lookback:]), signals


def fit_limits(engine: PaperEngine, weights: dict, margin: float) -> dict:
    """Scale weights to the engine's position, sector and leverage limits."""
    limits = engine.limits()
    cap = limits.max_position_pct / 100 * margin
    fitted = {name: max(-cap, min(cap, w)) for name, w in weights.items()}
    sectors: dict = {}
    for name in fitted:
        instrument = engine.instrument(name)
        sectors.setdefault(instrument.sector or instrument.asset_class, []).append(name)
    for names in sectors.values():
        gross = sum(abs(fitted[n]) for n in names)
        allowed = limits.max_sector_pct / 100 * margin
        if gross > allowed:
            for n in names:
                fitted[n] *= allowed / gross
    # Net exposure per currency: scale every pair that holds one over the cap.
    account_currency = engine.account()["currency"]
    allowed = limits.max_currency_pct / 100 * margin
    for _ in range(3):
        exposure: dict = {}
        for name, w in fitted.items():
            pair = engine.instrument(name).currency_pair
            if pair:
                exposure[pair[:3]] = exposure.get(pair[:3], 0.0) + w
                exposure[pair[3:]] = exposure.get(pair[3:], 0.0) - w
        over = {c: abs(v) for c, v in exposure.items()
                if c != account_currency and abs(v) > allowed}
        if not over:
            break
        for name in fitted:
            pair = engine.instrument(name).currency_pair
            hits = [over[c] for c in (pair[:3], pair[3:]) if pair and c in over]
            if hits:
                fitted[name] *= allowed / max(hits)
    # Broker margin: the positions together may not need more than equity.
    needed = sum(abs(w) * engine.instrument(n).margin_pct / 100 for n, w in fitted.items())
    if needed > margin:
        fitted = {n: w * margin / needed for n, w in fitted.items()}
    gross = sum(abs(w) for w in fitted.values())
    allowed = limits.max_gross_leverage * margin
    if gross > allowed:
        fitted = {n: w * allowed / gross for n, w in fitted.items()}
    return fitted


def _submit(engine, request, now) -> dict:
    order = engine.submit_order(request, now)
    match = REDUCED.search(order["reason"] or "") if order["status"] == "REJECTED" else None
    if match:
        # The risk engine named the most it accepts: take that instead.
        price = engine.mark(request.symbol)["price"]
        quantity = float(match.group(1)) * 0.99 / price
        if quantity > 0:
            order = engine.submit_order(replace(
                request, client_order_id=request.client_order_id + ":reduced",
                quantity=quantity), now)
    return order


def rebalance(engine: PaperEngine, data: dict, weights: dict, config: RunnerConfig,
              now: datetime) -> list[dict]:
    """Orders that move each position toward its weight at the next open."""
    limits = engine.limits()
    equity = engine.equity()
    held = {p["symbol"]: p["quantity"] for p in engine.positions()}
    threshold = config.portfolio.rebalance_threshold
    plans = []
    for name, candles in data.items():
        mark = engine.mark(name)
        if mark is None or equity <= 0:
            continue
        price = mark["price"]
        current = held.get(name, 0.0)
        weight = weights.get(name, 0.0)
        now_weight = current * price / equity
        order_id = f"{candles[-1].open_time.date().isoformat()}:{name}"
        # Orders from an earlier date are obsolete whatever today's signal is,
        # also when no new order is needed (the position is already close enough).
        for old in engine.orders():
            if (old["symbol"] == name and old["status"] in ("PENDING", "PARTIAL")
                    and not old["client_order_id"].startswith(order_id)):
                engine.cancel_order(old["client_order_id"], now)
        flips = (weight > 0) != (now_weight > 0) or (weight < 0) != (now_weight < 0)
        if not ((flips and (weight or now_weight)) or abs(weight - now_weight) >= threshold):
            continue
        target = weight * equity / price
        delta = target - current
        side = "BUY" if delta > 0 else "SELL"
        plan = {"market": name, "weight_from": now_weight, "weight_to": weight,
                "side": side, "quantity": abs(delta), "price": price}
        reduces = current != 0 and (target == 0 or (target > 0) == (current > 0)) \
            and abs(target) < abs(current)
        if reduces:
            request = OrderRequest(order_id, name, side, abs(delta), reduce_only=True,
                                   source="paper_runner")
        else:
            if len(candles) <= config.atr_period:
                plan.update(status="SKIPPED", reason="Not enough candles for ATR")
                plans.append(plan)
                continue
            distance = config.stop_atr * average_true_range(candles, config.atr_period)
            if not distance > 0:
                plan.update(status="SKIPPED", reason="ATR is zero: no stop distance")
                plans.append(plan)
                continue
            stop = price - distance if delta > 0 else price + distance
            if stop <= 0:
                plan.update(status="SKIPPED", reason="Stop would be at or below zero")
                plans.append(plan)
                continue
            # Risk at the stop on the added size stays under the engine's limit.
            same_side = current == 0 or (current > 0) == (target > 0)
            added = abs(target) - abs(current) if same_side else abs(target)
            most = limits.max_risk_per_trade_pct / 100 * config.margin * equity / distance
            capped = added > most
            if capped:
                added = most
                target = (abs(current) + added if same_side else added) * (1 if delta > 0 else -1)
                delta = target - current
            plan.update(quantity=abs(delta), stop_loss=stop,
                        risk_capped=capped)
            request = OrderRequest(order_id, name, side, abs(delta), stop_loss=stop,
                                   source="paper_runner")
        order = _submit(engine, request, now)
        plan.update(client_order_id=order["client_order_id"], status=order["status"],
                    reason=order["reason"])
        plans.append(plan)
    return plans


def run_daily(engine: PaperEngine, data: dict, markets, factory, config: RunnerConfig,
              strategy: str, now: datetime | None = None,
              given_signals: dict | None = None, blend: bool = False) -> dict:
    """One daily step; the result is also written to the engine's journal."""
    now = now or datetime.now(timezone.utc)
    for market in markets:
        engine.register_instrument(instrument_for(market))
    fed = feed_new_candles(engine, data)
    account = engine.account()
    report = {"time": now.isoformat(), "strategy": strategy, "candles_processed": fed,
              "kill_switch": bool(account["kill_switch"]),
              "kill_reason": account["kill_reason"], "signals": {}, "weights": {},
              "orders": []}
    if not account["kill_switch"]:
        weights, signals = latest_weights(data, markets, factory, config.portfolio,
                                          given_signals, blend)
        if given_signals is not None and not blend:
            # Fără decizie azi pentru o piață: poziția rămâne cum e.
            equity = engine.equity()
            held = {p["symbol"]: p["quantity"] for p in engine.positions()}
            for market in markets:
                if market.name not in given_signals:
                    mark = engine.mark(market.name)
                    weights[market.name] = (held.get(market.name, 0.0) * mark["price"] / equity
                                            if mark and equity > 0 else 0.0)
        weights = fit_limits(engine, weights, config.margin)
        report.update(signals=signals, weights=weights,
                      orders=rebalance(engine, data, weights, config, now))
    # Current positions only: today's orders fill at the next open.
    report["scenarios"] = run_scenarios(engine)
    summary = engine.summary()
    report.update(equity=summary["equity"], cash=summary["cash"],
                  gross_leverage=summary["gross_leverage"],
                  net_profit=summary["net_profit"],
                  initial_capital=summary["initial_capital"],
                  currency=summary["currency"])
    engine.record("daily_run", report, now)
    return report


def history(engine: PaperEngine) -> list[dict]:
    return [{"time": e["payload"]["time"], "equity": e["payload"]["equity"]}
            for e in engine.journal("daily_run")]


def render_report(engine: PaperEngine, report: dict) -> str:
    """Markdown status page: account, positions, today's orders, history."""
    money = report["currency"]
    start = report["initial_capital"]
    change = 100 * (report["equity"] / start - 1)
    lines = [
        "# BND paper trading (virtual money)",
        "",
        f"- Run: {report['time']} | strategy `{report['strategy']}`",
        f"- Equity: {report['equity']:,.2f} {money} (start {start:,.2f}, {change:+.2f}%)",
        f"- Gross leverage: {report['gross_leverage'] or 0:.2f}x | "
        f"candles processed: {report['candles_processed']}",
        "- Kill switch: " + (f"**ACTIVE** ({report['kill_reason']}); restart with a manual "
                             "run and reset_kill_switch = RESET-KILL-SWITCH" if report["kill_switch"] else "off"),
    ]
    if report.get("missing_data"):
        lines.append("- No data this run (not traded): " + ", ".join(report["missing_data"]))
    lines += [
        "",
        "## Positions",
        "",
    ]
    positions = engine.positions()
    if positions:
        lines += ["| Market | Quantity | Avg price | Last | Value | Weight | P&L | Stop |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for p in positions:
            last = engine.mark(p["symbol"])["price"]
            value = p["quantity"] * last
            stop = f"{p['stop_loss']:.4f}" if p["stop_loss"] else "-"
            lines.append(
                f"| {p['symbol']} | {p['quantity']:.4f} | {p['avg_price']:.4f} | {last:.4f} "
                f"| {value:,.2f} | {100 * value / report['equity']:+.1f}% "
                f"| {(last - p['avg_price']) * p['quantity']:+,.2f} | {stop} |")
    else:
        lines.append("No open positions.")
    lines += ["", "## Orders for the next open", ""]
    if report["orders"]:
        lines += ["| Market | Side | Weight now -> target | Status | Note |",
                  "|---|---|---|---|---|"]
        for o in report["orders"]:
            note = o.get("reason") or ("capped by risk at the stop" if o.get("risk_capped") else "")
            lines.append(f"| {o['market']} | {o['side']} | {100 * o['weight_from']:+.1f}% -> "
                         f"{100 * o['weight_to']:+.1f}% | {o['status']} | {note} |")
    else:
        lines.append("No changes.")
    if engine.positions():
        lines += ["", "## Stress scenarios (instant shock to current positions)", "",
                  "| Scenario | Equity change | Biggest loser | Kill switch |",
                  "|---|---:|---|---|"]
        lines += [f"| {row['description']} | {row['change_pct']:+.1f}% | "
                  f"{row['worst_market'] or '-'} | "
                  f"{'would trip' if row['beyond_kill_switch'] else 'no'} |"
                  for row in report.get("scenarios", [])]
    past = history(engine)[-30:]
    if len(past) > 1:
        lines += ["", "## Equity, last runs", "", "| Run | Equity |", "|---|---:|"]
        lines += [f"| {row['time'][:10]} | {row['equity']:,.2f} |" for row in past]
    lines += ["", "_Virtual money only. Backtests found no proven edge; this record "
                  "is the forward test, not proof of profit._", ""]
    return "\n".join(lines)


# Trading settings, fixed when the account is created so every later run
# (including unattended scheduled ones) trades the same way.
DEFAULTS = {
    "universe": "etf", "markets": None, "classes": None,
    "strategy": "regime_switch", "members": None, "param": [], "portfolio_vol": 15.0,
    "sizing_lookback": 60, "max_leverage": 3.0, "max_weight": 1.0,
    "rebalance": 5.0, "no_shorts": False, "stop_atr": 3.0, "financing": 5.0,
    "max_sector": None,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paper_runner", description="One daily paper-trading step. Trading "
        "settings apply when the account is created and are stored in it.")
    parser.add_argument("--state", required=True, help="SQLite paper account")
    parser.add_argument("--capital", type=float,
                        help="virtual starting capital; only to create a new account")
    parser.add_argument("--currency", default="USD",
                        help="account currency label for a new account (prices are in USD)")
    parser.add_argument("--data-dir", required=True, help="CSV per market (fetch-universe)")
    parser.add_argument("--report", help="write the Markdown status page here")
    parser.add_argument("--json", help="write this run's result here")
    parser.add_argument("--audit-log", help="append a hash-chained audit entry here")
    parser.add_argument("--reset-kill-switch", metavar="CONFIRMATION",
                        help="restart after a kill switch; the text must be RESET-KILL-SWITCH")
    # Settings default to None so an explicit value can be told apart.
    parser.add_argument("--universe", choices=["futures", "etf", "stocks", "crypto", "ai", "unic"])
    parser.add_argument("--markets")
    parser.add_argument("--classes")
    parser.add_argument("--strategy",
                        choices=["combo", "selector", "score_weighted", "cross_momentum", "ai_council", "hibrid"]
                        + sorted(SWEEP_RANGES))
    parser.add_argument("--members", help="combo/selector: comma-separated strategies")
    parser.add_argument("--param", action="append", metavar="NAME=VALUE")
    parser.add_argument("--portfolio-vol", type=float)
    parser.add_argument("--sizing-lookback", type=int)
    parser.add_argument("--max-leverage", type=float)
    parser.add_argument("--max-weight", type=float)
    parser.add_argument("--rebalance", type=float)
    parser.add_argument("--no-shorts", action="store_const", const=True)
    parser.add_argument("--stop-atr", type=float)
    parser.add_argument("--financing", type=float,
                        help="annual %% on exposure above equity (margin loan), default 5; "
                             "applies when the account is created")
    parser.add_argument("--max-sector", type=float,
                        help="limita de expunere pe un sector/clasă, %% din cont (la crearea contului)")
    parser.add_argument("--signals", help="fișier JSON cu semnale (strategia ai_council)")
    return parser


def _given(args) -> dict:
    return {key: getattr(args, key) for key in DEFAULTS if getattr(args, key) is not None}


def _stored_settings(engine) -> dict:
    entries = engine.journal("runner_settings")
    if not entries:
        raise ValueError("Account has no stored runner settings")
    return entries[-1]["payload"]


def _open_account(args) -> tuple[PaperEngine, dict]:
    given = _given(args)
    if Path(args.state).exists():
        if args.capital is not None:
            raise ValueError("Account already exists; --capital is only for a new one")
        engine = PaperEngine.open(args.state)
        settings = _stored_settings(engine)
        changed = sorted(k for k, v in given.items() if settings.get(k) != v)
        if changed:
            engine.close()
            raise ValueError("Account was created with other settings (" + ", ".join(changed)
                             + "); start a new account to change them")
        return engine, settings
    if args.capital is None:
        raise ValueError("No paper account yet: confirm the virtual starting capital "
                         "with --capital")
    settings = {**DEFAULTS, **given}
    _config(settings)                                      # fail before creating
    _make_factory(settings, {})                            # fail before creating
    Path(args.state).parent.mkdir(parents=True, exist_ok=True)
    engine = PaperEngine.create(args.state, args.capital, currency=args.currency,
                                limits=EngineLimits(financing_pct_annual=settings["financing"],
                                        **({"max_sector_pct": settings["max_sector"]}
                                           if settings.get("max_sector") else {})))
    engine.record("runner_settings", settings, datetime.now(timezone.utc))
    return engine, settings


def _params(settings) -> dict:
    params = {k: parse_value(v) for k, v in _pairs(settings["param"], "--param").items()}
    if settings.get("members"):
        if settings["strategy"] not in ("combo", "selector", "score_weighted"):
            raise ValueError("--members is only for --strategy combo or selector")
        params["members"] = tuple(_split_list(settings["members"]))
    return params


def _make_factory(settings, data):
    if settings["strategy"] == "ai_council":
        return lambda: (lambda history: 0.0)          # semnalele vin din fișier
    params = _params(settings)
    if settings["strategy"] != "cross_momentum":
        # „hibrid” = regulile regime_switch amestecate cu semnalele consiliului AI.
        factory = _factory("regime_switch" if settings["strategy"] == "hibrid" else settings["strategy"], params)
        if not data:
            factory()
        return factory
    try:
        return cross_momentum_factory(data, **params)
    except TypeError as exc:
        raise ValueError(f"Invalid parameters for cross_momentum: {exc}") from exc


def _config(settings) -> RunnerConfig:
    return RunnerConfig(
        portfolio=PortfolioConfig(
            target_vol_pct=settings["portfolio_vol"], vol_lookback=settings["sizing_lookback"],
            max_leverage=settings["max_leverage"], max_weight=settings["max_weight"],
            rebalance_threshold=settings["rebalance"] / 100,
            allow_short=not settings["no_shorts"]),
        stop_atr=settings["stop_atr"])


def _read_signals(path) -> dict:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        signals = payload["signals"]
        values = {str(k): float(v) for k, v in signals.items()}
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Fișier de semnale invalid: {exc}") from exc
    if any(not -1.0 <= v <= 1.0 for v in values.values()):
        raise ValueError("Semnalele trebuie să fie între -1 și 1")
    return values


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        mode = trading_mode()
        engine, settings = _open_account(args)
        try:
            if args.reset_kill_switch is not None:
                if not engine.account()["kill_switch"]:
                    raise ValueError("Kill switch is not active; nothing to reset")
                engine.reset_kill_switch(args.reset_kill_switch, datetime.now(timezone.utc))
            config = _config(settings)
            markets = select_markets(_split_list(settings["markets"]),
                                     _split_list(settings["classes"]), settings["universe"])
            folder = Path(args.data_dir)
            available = [m for m in markets if (folder / f"{m.name}.csv").exists()]
            if not available:
                raise ValueError("No market data found in " + str(folder))
            data = {m.name: load_csv(folder / f"{m.name}.csv") for m in available}
            factory = _make_factory(settings, data)
            given = None
            if settings["strategy"] in ("ai_council", "hibrid"):
                if not args.signals:
                    raise ValueError(f"Strategia {settings['strategy']} cere --signals")
                given = _read_signals(args.signals)
            report = run_daily(engine, data, available, factory, config, settings["strategy"],
                               given_signals=given, blend=settings["strategy"] == "hibrid")
            report["settings"] = settings
            report["mode"] = mode
            if args.audit_log:
                audit_log.append(args.audit_log, "daily_run", {
                    "mode": mode, "strategy": settings["strategy"],
                    "equity": report["equity"], "orders": len(report["orders"]),
                    "kill_switch": report["kill_switch"],
                    "candles_processed": report["candles_processed"]})
            report["missing_data"] = [m.name for m in markets if m not in available]
            if args.report:
                Path(args.report).write_text(render_report(engine, report))
        finally:
            engine.close()
    except (MarketDataError, PaperEngineError, SafetyError, ValueError) as exc:
        print("Error:", exc, file=sys.stderr)
        return 2
    text = json.dumps(report, indent=2, default=str)
    if args.json:
        Path(args.json).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
