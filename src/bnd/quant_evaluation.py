"""Offline strategy evaluation helpers; no market connectivity or trading."""
import csv
from datetime import datetime, timezone
from pathlib import Path

from .quant_backtest import Bar, BacktestConfig, backtest, walk_forward_splits


def load_ohlc_csv(path: str | Path) -> list[Bar]:
    """Read ordered bars from a CSV with timestamp,open,close columns.

    Parse ISO timestamps and compare in UTC, not lexicographic string order.
    Date-only/naive ISO timestamps are interpreted as UTC. Callers must
    validate source, interval consistency and market-specific adjustments.
    """
    bars = []
    previous = None
    with open(path, newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not {"timestamp", "open", "close"}.issubset(reader.fieldnames):
            raise ValueError("CSV requires timestamp, open, close")
        for row in reader:
            stamp = row["timestamp"]
            if not isinstance(stamp, str) or not stamp.strip():
                raise ValueError("Timestamp must be a nonempty ISO string")
            try:
                parsed = datetime.fromisoformat(stamp.strip().replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Invalid ISO timestamp") from exc
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            instant = parsed.astimezone(timezone.utc)
            if previous is not None and instant <= previous:
                raise ValueError("Timestamps must be unique and strictly increasing in UTC")
            previous = instant
            bars.append(Bar(float(row["open"]), float(row["close"])))
    if len(bars) < 2:
        raise ValueError("At least two bars are required")
    return bars


def sma_signals(bars: list[Bar], window: int) -> list[bool]:
    """Signal at close: long if close exceeds SMA, else flat."""
    if type(window) is not int or window < 2:
        raise ValueError("Window must be >=2")
    result = []
    running = 0.0
    for i, bar in enumerate(bars):
        running += bar.close
        if i >= window:
            running -= bars[i-window].close
        result.append(i + 1 >= window and bar.close > running / window)
    return result


def buy_and_hold(bars: list[Bar], config: BacktestConfig = BacktestConfig()) -> dict:
    """Fair next-open buy-and-hold benchmark using identical fee/slippage rules."""
    return backtest(bars, [True] * len(bars), config)


def evaluate_sma_walk_forward(bars: list[Bar], window: int, train_size: int,
                              test_size: int, config: BacktestConfig = BacktestConfig()) -> list[dict]:
    """Evaluate fixed SMA settings in forward test folds, including warm-up.

    Test fold starts at its first bar open using only preceding close signals.
    Never tune window on test results. Folds are independently funded.
    """
    if type(window) is not int or window < 2 or window > train_size:
        raise ValueError("SMA window must be an integer between 2 and train_size")
    folds = walk_forward_splits(len(bars), train_size, test_size)
    reports = []
    for train, test in folds:
        first = train.start
        last = test.stop
        segment = bars[first:last]
        signals = sma_signals(segment, window)
        # No trading during training; first execution at test's first open.
        signals = [False] * (train_size - 1) + signals[train_size - 1:]
        # Use training bars as warm-up without accounting for their returns.
        test_bars = segment[train_size - 1:]
        test_signals = signals[train_size - 1:]
        strategy = backtest(test_bars, test_signals, config)
        benchmark = buy_and_hold(test_bars, config)
        reports.append({
            "train_start": train.start, "train_end": train.stop,
            "test_start": test.start, "test_end": test.stop,
            "strategy": strategy, "benchmark": benchmark,
            "excess_net_return_pct": strategy["net_return_pct"] - benchmark["net_return_pct"],
        })
    return reports
