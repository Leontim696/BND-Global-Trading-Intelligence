"""Walk-forward optimisation: re-choose parameters on past data only.

For each fold the parameter grid is evaluated on the training window
alone; the best set (by Sharpe) is then traded on the following test
window, which starts ``embargo`` candles after training ends so no
information leaks across. Test windows never overlap, so their returns
can be chained into one out-of-sample record.

Optional degradation switch-off: when the average Sharpe of the last
``disable_after`` test folds is below ``disable_below``, the next fold is
skipped (flat), and trading resumes once the strategy's own simulated
results recover. Both the plain and the switched records are reported so
the rule can be judged rather than assumed.
"""

from statistics import mean
from typing import Callable, Sequence

from .backtester import BacktestConfig, run_backtest
from .market_data import Candle
from .robustness import parameter_grid
from .strategies import buy_and_hold


def folds(length: int, train: int, test: int, embargo: int = 0,
          mode: str = "rolling") -> list[tuple[int, int, int, int]]:
    """(train_start, train_end, test_start, test_end) index ranges."""

    if mode not in ("rolling", "expanding"):
        raise ValueError("mode must be 'rolling' or 'expanding'")
    if min(train, test) < 2 or embargo < 0:
        raise ValueError("train and test need at least 2 candles; embargo >= 0")
    result, train_end = [], train
    while train_end + embargo + test <= length:
        start = 0 if mode == "expanding" else train_end - train
        test_start = train_end + embargo
        result.append((start, train_end, test_start, test_start + test))
        train_end += test
    if not result:
        raise ValueError("Not enough candles for one fold")
    return result


def _score(row) -> float:
    return row["sharpe"] if row["sharpe"] is not None else float("-inf")


def walk_forward(
    candles: Sequence[Candle],
    factory: Callable,
    param_sets: Sequence[dict],
    config: BacktestConfig,
    train: int,
    test: int,
    embargo: int = 0,
    mode: str = "rolling",
    disable_below: float | None = 0.0,
    disable_after: int = 2,
) -> dict:
    candles = list(candles)
    plan = folds(len(candles), train, test, embargo, mode)
    rows = []
    for train_start, train_end, test_start, test_end in plan:
        grid = parameter_grid(candles[train_start:train_end], factory, param_sets, config)
        best = max(grid, key=_score)
        # Warm up on the candles before the test window; trade only inside it.
        window = candles[train_start:test_end]
        result = run_backtest(window, factory(**best["params"]), config,
                              trade_from=test_start - train_start)
        # Same window, same costs, no risk gate: the bar to beat.
        benchmark = run_backtest(window, buy_and_hold(),
                                 BacktestConfig(initial_equity=config.initial_equity,
                                                costs=config.costs),
                                 trade_from=test_start - train_start)
        rows.append({
            "train": [candles[train_start].open_time.isoformat(),
                      candles[train_end - 1].open_time.isoformat()],
            "test": [candles[test_start].open_time.isoformat(),
                     candles[test_end - 1].open_time.isoformat()],
            "params": best["params"],
            "train_sharpe": best["sharpe"],
            "test_return_pct": result.metrics["total_return_pct"],
            "test_sharpe": result.metrics["sharpe"],
            "test_max_drawdown_pct": result.metrics["max_drawdown_pct"],
            "test_trades": result.metrics["trades"],
            "buy_and_hold_return_pct": benchmark.metrics["total_return_pct"],
            "buy_and_hold_sharpe": benchmark.metrics["sharpe"],
        })

    def chain(returns):
        value = 1.0
        for r in returns:
            value *= 1 + r / 100
        return 100 * (value - 1)

    # Degradation switch-off, decided only from folds already finished.
    active = []
    for i, row in enumerate(rows):
        recent = [r["test_sharpe"] or 0.0 for r in rows[max(0, i - disable_after):i]]
        off = (disable_below is not None and len(recent) == disable_after
               and mean(recent) < disable_below)
        row["switched_off"] = off
        active.append(0.0 if off else row["test_return_pct"])

    changes = sum(a["params"] != b["params"] for a, b in zip(rows, rows[1:]))
    sharpes = [r["test_sharpe"] for r in rows if r["test_sharpe"] is not None]
    return {
        "mode": mode,
        "train": train,
        "test": test,
        "embargo": embargo,
        "folds": rows,
        "summary": {
            "fold_count": len(rows),
            "chained_test_return_pct": chain(r["test_return_pct"] for r in rows),
            "chained_return_with_switch_off_pct": chain(active),
            "chained_buy_and_hold_return_pct": chain(r["buy_and_hold_return_pct"] for r in rows),
            "folds_beating_buy_and_hold": sum(
                r["test_return_pct"] > r["buy_and_hold_return_pct"] for r in rows),
            "folds_switched_off": sum(r["switched_off"] for r in rows),
            "positive_folds": sum(r["test_return_pct"] > 0 for r in rows),
            "mean_test_sharpe": mean(sharpes) if sharpes else None,
            "mean_train_sharpe": mean(r["train_sharpe"] for r in rows
                                      if r["train_sharpe"] is not None)
            if any(r["train_sharpe"] is not None for r in rows) else None,
            # 0 = the same parameters every fold, 1 = a new choice every time.
            "parameter_change_rate": changes / (len(rows) - 1) if len(rows) > 1 else 0.0,
            "distinct_parameter_sets": len({tuple(sorted(r["params"].items())) for r in rows}),
        },
        "note": ("Parameters are chosen on each training window only. A large gap "
                 "between mean train and test Sharpe, or a high change rate, signals "
                 "overfitting."),
    }
