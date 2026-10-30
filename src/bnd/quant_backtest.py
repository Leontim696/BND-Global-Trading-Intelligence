"""Deterministic, offline, long-only paper backtesting foundation.

Signals are decided using the current close and executed at the NEXT bar open.
No broker connectivity, leverage, optimization, or live execution.
"""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class Bar:
    open: float
    close: float

    def __post_init__(self):
        if any(not isinstance(x, (int, float)) or isinstance(x, bool)
               or not isfinite(x) or x <= 0 for x in (self.open, self.close)):
            raise ValueError("Prices must be positive finite numbers")


@dataclass(frozen=True)
class BacktestConfig:
    starting_cash: float = 10000.0
    fee_bps: float = 10.0
    slippage_bps: float = 5.0

    def __post_init__(self):
        if not isfinite(self.starting_cash) or self.starting_cash <= 0:
            raise ValueError("Starting cash must be positive")
        for value in (self.fee_bps, self.slippage_bps):
            if not isfinite(value) or value < 0 or value >= 10000:
                raise ValueError("Invalid transaction cost")


def backtest(bars: list[Bar], signals: list[bool], config: BacktestConfig = BacktestConfig()) -> dict:
    """At bar i open, execute signal from bar i-1 close; mark at final close.

    The first signal cannot trade until the second bar. Fractional units permitted.
    """
    if len(bars) < 2 or len(signals) != len(bars):
        raise ValueError("Need >=2 bars and one signal per bar")
    if any(type(signal) is not bool for signal in signals):
        raise ValueError("Signals must be booleans")
    cash, units = float(config.starting_cash), 0.0
    peak, max_drawdown = cash, 0.0
    fees_paid, trades = 0.0, 0
    slip = config.slippage_bps / 10000
    fee = config.fee_bps / 10000
    curve = []
    for i, bar in enumerate(bars):
        if i > 0:
            desired = signals[i - 1]
            if desired and units == 0:
                execution = bar.open * (1 + slip)
                units = cash / (execution * (1 + fee))
                fees_paid += units * execution * fee
                cash = 0.0
                trades += 1
            elif not desired and units > 0:
                execution = bar.open * (1 - slip)
                gross = units * execution
                fees_paid += gross * fee
                cash = gross * (1 - fee)
                units = 0.0
                trades += 1
        equity = cash + units * bar.close
        curve.append(equity)
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak)
    final_equity = curve[-1]
    return {
        "starting_cash": config.starting_cash,
        "final_equity": final_equity,
        "net_return_pct": 100 * (final_equity / config.starting_cash - 1),
        "max_drawdown_pct": 100 * max_drawdown,
        "fees_paid": fees_paid,
        "execution_count": trades,
        "equity_curve": curve,
        "open_units": units,
        "note": "Offline paper-only; no market data feed or order execution",
    }


def walk_forward_splits(length: int, train_size: int, test_size: int, step: int | None = None) -> list[tuple[range, range]]:
    """Non-overlapping train/test per fold; test windows can overlap only if step < test_size."""
    if any(type(x) is not int or x <= 0 for x in (length, train_size, test_size)):
        raise ValueError("Sizes must be positive integers")
    if step is None:
        step = test_size
    if type(step) is not int or step <= 0:
        raise ValueError("Step must be a positive integer")
    return [
        (range(end - train_size, end), range(end, end + test_size))
        for end in range(train_size, length - test_size + 1, step)
    ]
