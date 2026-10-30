"""Walk-forward optimisation of a whole multi-market portfolio.

Folds are calendar windows: ``train_days`` to choose the parameters (best
portfolio Sharpe on that window only), then ``test_days`` of trading with
them, starting ``embargo_days`` after training ends. Each window sees all
earlier candles as warm-up, but nothing after its end. Every test window
is compared with the equal-weight basket on the same dates, and the test
results are chained into one out-of-sample record.

Each window starts from fresh equity, so a kill switch in one fold does
not carry into the next: the chained figure is what a trader who
re-optimised once a year and restarted after a stop would have seen.
"""

from datetime import datetime, timedelta
from statistics import mean
from typing import Callable, Mapping, Sequence

from .market_data import Candle
from .portfolio import PortfolioConfig, run_portfolio, strategy_for
from .strategies import buy_and_hold
from .universe import Market


def calendar_folds(times: Sequence[datetime], train_days: int, test_days: int,
                   embargo_days: int = 0) -> list[tuple[datetime, datetime, datetime, datetime]]:
    """(train_start, train_end, test_start, test_end); ends are exclusive."""
    if train_days < 30 or test_days < 30 or embargo_days < 0:
        raise ValueError("Require train_days >= 30, test_days >= 30, embargo_days >= 0")
    first, last = times[0], times[-1]
    folds, start = [], first
    while True:
        train_end = start + timedelta(days=train_days)
        test_start = train_end + timedelta(days=embargo_days)
        test_end = test_start + timedelta(days=test_days)
        if test_end > last + timedelta(days=1):
            break
        folds.append((start, train_end, test_start, test_end))
        start += timedelta(days=test_days)
    if not folds:
        raise ValueError("Not enough history for one fold")
    return folds


def _window(data, markets, end, minimum):
    """Candles before ``end``; markets with too little history are left out."""
    cut = {m.name: [c for c in data[m.name] if c.open_time < end] for m in markets}
    usable = [m for m in markets if len(cut[m.name]) >= minimum]
    return {m.name: cut[m.name] for m in usable}, usable


def _run(data, markets, factory, config, start, end, minimum):
    frame, usable = _window(data, markets, end, minimum)
    times = sorted({c.open_time for candles in frame.values() for c in candles
                    if c.open_time >= start})
    if len(usable) < 2 or len(times) < 3:
        return None
    first = min(candles[0].open_time for candles in frame.values())
    # No earlier candles to warm up on (first fold): trade from the start.
    trade_from = times[0] if times[0] > first else None
    try:
        return run_portfolio(frame, usable, factory, config, trade_from=trade_from)
    except ValueError:
        return None


def _members(frame, members):
    return {m.name: frame[m.name] for m in members if m.name in frame}


def _by_class(choices, make_factory, frame, markets):
    """One portfolio factory that gives each market its asset class's parameters."""
    factories = {cls: make_factory(params, _members(frame, [m for m in markets
                                                             if m.asset_class == cls]))
                 for cls, params in choices.items()}

    def factory(market):
        return strategy_for(factories[market.asset_class], market)

    factory.per_market = True
    return factory


def _sharpe(result) -> float:
    if result is None or result["metrics"]["sharpe"] is None:
        return float("-inf")
    return result["metrics"]["sharpe"]


def portfolio_walk_forward(
    data: Mapping[str, Sequence[Candle]],
    markets: Sequence[Market],
    make_factory: Callable[[dict, Mapping], Callable],
    param_sets: Sequence[dict],
    config: PortfolioConfig,
    train_days: int = 4 * 365,
    test_days: int = 365,
    embargo_days: int = 5,
    per_class: bool = False,
) -> dict:
    """``make_factory(params, frame)`` builds a portfolio factory for one window.

    With ``per_class`` each asset class gets its own parameter set, chosen on
    the training window of that class's markets alone (a cross-sectional
    strategy then ranks markets within their class).
    """
    if not param_sets:
        raise ValueError("At least one parameter set is required")
    times = sorted({c.open_time for m in markets for c in data[m.name]})
    minimum = config.vol_lookback + 2
    basket = PortfolioConfig(initial_equity=config.initial_equity, sizing="equal",
                             max_leverage=1.0, max_weight=1.0, max_drawdown_pct=None,
                             allow_short=False, vol_lookback=config.vol_lookback)
    rows = []
    for train_start, train_end, test_start, test_end in calendar_folds(
            times, train_days, test_days, embargo_days):
        frame, _ = _window(data, markets, train_end, minimum)
        if per_class:
            best = {}
            for cls in sorted({m.asset_class for m in markets}):
                members = [m for m in markets if m.asset_class == cls]
                own = _members(frame, members)
                scored = [(params, _run(data, members, make_factory(params, own), config,
                                        train_start, train_end, minimum))
                          for params in param_sets]
                best[cls] = max(scored, key=lambda item: _sharpe(item[1]))[0]
            trained = _run(data, markets, _by_class(best, make_factory, frame, markets),
                           config, train_start, train_end, minimum)
        else:
            scored = [(params, _run(data, markets, make_factory(params, frame), config,
                                    train_start, train_end, minimum))
                      for params in param_sets]
            best, trained = max(scored, key=lambda item: _sharpe(item[1]))
        frame, _ = _window(data, markets, test_end, minimum)
        factory = (_by_class(best, make_factory, frame, markets) if per_class
                   else make_factory(best, frame))
        tested = _run(data, markets, factory, config, test_start, test_end, minimum)
        bench = _run(data, markets, buy_and_hold, basket, test_start, test_end, minimum)
        if tested is None or bench is None:
            continue
        rows.append({
            "train": [train_start.date().isoformat(), train_end.date().isoformat()],
            "test": [test_start.date().isoformat(), test_end.date().isoformat()],
            "params": best,
            "train_sharpe": _sharpe(trained) if trained else None,
            "markets": tested["metrics"]["markets"],
            "test_return_pct": tested["metrics"]["total_return_pct"],
            "test_sharpe": tested["metrics"]["sharpe"],
            "test_max_drawdown_pct": tested["metrics"]["max_drawdown_pct"],
            "kill_switch_at": tested["metrics"]["kill_switch_at"],
            "basket_return_pct": bench["metrics"]["total_return_pct"],
            "basket_sharpe": bench["metrics"]["sharpe"],
        })
    if not rows:
        raise ValueError("No fold had enough markets and dates")

    def chain(values):
        total = 1.0
        for value in values:
            total *= 1 + value / 100
        return 100 * (total - 1)

    sharpes = [r["test_sharpe"] for r in rows if r["test_sharpe"] is not None]
    trains = [r["train_sharpe"] for r in rows
              if r["train_sharpe"] not in (None, float("-inf"))]
    changes = sum(a["params"] != b["params"] for a, b in zip(rows, rows[1:]))
    return {
        "train_days": train_days, "test_days": test_days, "embargo_days": embargo_days,
        "per_class": per_class,
        "folds": rows,
        "summary": {
            "fold_count": len(rows),
            "chained_test_return_pct": chain(r["test_return_pct"] for r in rows),
            "chained_basket_return_pct": chain(r["basket_return_pct"] for r in rows),
            "folds_beating_basket": sum(r["test_return_pct"] > r["basket_return_pct"]
                                        for r in rows),
            "positive_folds": sum(r["test_return_pct"] > 0 for r in rows),
            "folds_with_kill_switch": sum(r["kill_switch_at"] is not None for r in rows),
            "mean_train_sharpe": mean(trains) if trains else None,
            "mean_test_sharpe": mean(sharpes) if sharpes else None,
            "mean_basket_sharpe": mean(r["basket_sharpe"] for r in rows
                                       if r["basket_sharpe"] is not None),
            "parameter_change_rate": changes / (len(rows) - 1) if len(rows) > 1 else 0.0,
        },
        "note": ("Parameters are chosen on each training window only; each test "
                 "window starts from fresh equity. A large gap between mean train "
                 "and test Sharpe signals overfitting."),
    }
