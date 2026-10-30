"""BND Backtester — event-driven simulation on OHLCV candles.

Rules that prevent look-ahead bias:
- A strategy sees only candles up to and including the current one.
- Its decision is executed at the NEXT candle's open.
- Stop losses are checked against each candle's high/low; a gap
  through the stop fills at the (worse) open price.

Every fill pays a fee and slippage. Position size is approved by the
deterministic risk engine, which has veto power over every entry.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import isfinite, sqrt
from statistics import median
from collections.abc import Sequence as SequenceABC
from typing import Callable, Sequence

from .market_data import Candle, validate_series
from .risk_engine import (
    Portfolio,
    RiskDecision,
    RiskLimits,
    TradeProposal,
    evaluate_risk,
)

# Target position: 1 = long, 0 = flat, -1 = short.
Strategy = Callable[[Sequence[Candle]], int]

SECONDS_PER_YEAR = 365.25 * 24 * 3600


@dataclass(frozen=True)
class CostModel:
    """Percent costs applied to every fill."""

    fee_pct: float = 0.10
    slippage_pct: float = 0.05

    def __post_init__(self):
        for value in (self.fee_pct, self.slippage_pct):
            if not isfinite(value) or not 0 <= value < 10:
                raise ValueError("Costs must be in [0, 10) percent")


@dataclass(frozen=True)
class BacktestConfig:
    initial_equity: float = 10_000.0
    costs: CostModel = field(default_factory=CostModel)
    # Fraction of equity requested per entry, before risk checks.
    allocation_pct: float = 100.0
    # Optional protective stop; also used by the risk engine for sizing.
    stop_loss_pct: float | None = None
    allow_short: bool = False
    risk_limits: RiskLimits | None = None

    def __post_init__(self):
        if not isfinite(self.initial_equity) or self.initial_equity <= 0:
            raise ValueError("Initial equity must be positive")

        if not isfinite(self.allocation_pct) or not 0 < self.allocation_pct <= 100:
            raise ValueError("Allocation must be in (0, 100] percent")

        if self.stop_loss_pct is not None and (
            not isfinite(self.stop_loss_pct)
            or not 0 < self.stop_loss_pct < 100
        ):
            raise ValueError("Stop loss must be in (0, 100) percent")

        if self.risk_limits is not None and self.stop_loss_pct is None:
            raise ValueError("Risk limits require a stop loss for sizing")


@dataclass(frozen=True)
class Trade:
    side: int
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    quantity: float
    pnl: float
    fees: float
    exit_reason: str


@dataclass(frozen=True)
class BacktestResult:
    trades: list[Trade]
    equity_curve: list[tuple[datetime, float]]
    metrics: dict
    rejected_entries: int


class _History(SequenceABC):
    """Read-only view of candles[:end] that cannot reach later candles."""

    def __init__(self, candles: Sequence[Candle], end: int):
        self._candles = candles
        self._end = end

    def __len__(self) -> int:
        return self._end

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self._candles[i] for i in range(*index.indices(self._end))]
        if index < 0:
            index += self._end
        if not 0 <= index < self._end:
            raise IndexError("History index out of range")
        return self._candles[index]


def _bars_per_year(candles: Sequence[Candle]) -> float:
    if len(candles) < 2:
        return 0.0
    steps = [
        (b.open_time - a.open_time).total_seconds()
        for a, b in zip(candles, candles[1:])
    ]
    return SECONDS_PER_YEAR / median(steps)


def compute_metrics(
    equity_curve: Sequence[tuple[datetime, float]],
    trades: Sequence[Trade],
    bars_per_year: float,
    initial_equity: float,
    risk_free_rate_annual: float = 0.0,
) -> dict:
    equities = [value for _, value in equity_curve]
    final = equities[-1] if equities else initial_equity

    peak = initial_equity
    max_drawdown = 0.0
    for value in equities:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, (peak - value) / peak)

    returns = [
        b / a - 1
        for a, b in zip([initial_equity] + equities, equities)
        if a > 0
    ]
    sharpe = None
    if len(returns) >= 2 and bars_per_year > 0:
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        if variance > 0:
            rf = (1 + risk_free_rate_annual) ** (1 / bars_per_year) - 1
            sharpe = (mean - rf) / sqrt(variance) * sqrt(bars_per_year)

    years = len(equities) / bars_per_year if bars_per_year > 0 else 0
    cagr = None
    if years > 0 and final > 0:
        cagr = (final / initial_equity) ** (1 / years) - 1

    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [t.pnl for t in trades if t.pnl <= 0]
    gross_loss = -sum(losses)

    return {
        "initial_equity": initial_equity,
        "final_equity": final,
        "total_return_pct": 100 * (final / initial_equity - 1),
        "cagr_pct": None if cagr is None else 100 * cagr,
        "max_drawdown_pct": 100 * max_drawdown,
        "sharpe": sharpe,
        "trades": len(trades),
        "win_rate_pct": 100 * len(wins) / len(trades) if trades else None,
        "profit_factor": sum(wins) / gross_loss if gross_loss > 0 else None,
        "total_fees": sum(t.fees for t in trades),
        "bars": len(equities),
        "years": years,
        "risk_free_rate_annual": risk_free_rate_annual,
    }


class _Simulator:
    def __init__(self, candles: Sequence[Candle], config: BacktestConfig):
        self.candles = candles
        self.config = config
        self.cash = config.initial_equity
        self.quantity = 0.0
        self.side = 0
        self.entry_time: datetime | None = None
        self.entry_price = 0.0
        self.entry_fee = 0.0
        self.stop_price: float | None = None
        self.trades: list[Trade] = []
        self.rejected_entries = 0
        self.peak = config.initial_equity
        self.day = None
        self.day_start_equity = config.initial_equity
        # Equity at the previous candle's close (last valuation mark).
        self.last_mark = config.initial_equity

    def equity(self, price: float) -> float:
        return self.cash + self.quantity * price

    def _fill(self, price: float, side: int) -> float:
        # Buying pays up, selling receives less.
        slip = self.config.costs.slippage_pct / 100
        return price * (1 + slip) if side > 0 else price * (1 - slip)

    def _fee(self, notional: float) -> float:
        return abs(notional) * self.config.costs.fee_pct / 100

    def open_position(self, side: int, candle: Candle) -> None:
        equity = self.equity(candle.open)
        if equity <= 0:
            # Account wiped out (e.g. a short gapped through its stop).
            self.rejected_entries += 1
            return
        notional = equity * self.config.allocation_pct / 100

        if self.config.risk_limits is not None:
            risk = evaluate_risk(
                Portfolio(
                    equity=equity,
                    daily_loss=max(0.0, self.day_start_equity - equity),
                    drawdown=max(0.0, self.peak - equity),
                    gross_exposure=0.0,
                ),
                TradeProposal(
                    notional=notional,
                    stop_loss_pct=self.config.stop_loss_pct,
                    leverage=1.0,
                ),
                self.config.risk_limits,
            )
            if risk.decision == RiskDecision.REJECT:
                self.rejected_entries += 1
                return
            notional = risk.approved_notional

        price = self._fill(candle.open, side)
        # Keep the entry fee inside the approved notional.
        quantity = notional / (price * (1 + self.config.costs.fee_pct / 100))
        fee = self._fee(quantity * price)

        self.quantity = side * quantity
        self.cash -= self.quantity * price + fee
        self.side = side
        self.entry_time = candle.open_time
        self.entry_price = price
        self.entry_fee = fee

        if self.config.stop_loss_pct is not None:
            distance = self.config.stop_loss_pct / 100
            self.stop_price = price * (1 - side * distance)

    def close_position(self, time: datetime, raw_price: float, reason: str) -> None:
        price = self._fill(raw_price, -self.side)
        fee = self._fee(self.quantity * price)
        self.cash += self.quantity * price - fee
        pnl = self.quantity * (price - self.entry_price) - self.entry_fee - fee

        self.trades.append(Trade(
            side=self.side,
            entry_time=self.entry_time,
            entry_price=self.entry_price,
            exit_time=time,
            exit_price=price,
            quantity=abs(self.quantity),
            pnl=pnl,
            fees=self.entry_fee + fee,
            exit_reason=reason,
        ))

        self.quantity = 0.0
        self.side = 0
        self.stop_price = None

    def check_stop(self, candle: Candle) -> bool:
        if self.stop_price is None:
            return False

        if self.side > 0 and candle.low <= self.stop_price:
            self.close_position(
                candle.open_time, min(candle.open, self.stop_price), "stop_loss"
            )
            return True

        if self.side < 0 and candle.high >= self.stop_price:
            self.close_position(
                candle.open_time, max(candle.open, self.stop_price), "stop_loss"
            )
            return True

        return False

    def start_bar(self, candle: Candle) -> None:
        # Daily P&L policy: UTC calendar day measured from the previous
        # day's final close mark, so an overnight gap counts against the
        # new day's loss limit.
        day = candle.open_time.astimezone(timezone.utc).date()
        if day != self.day:
            self.day = day
            self.day_start_equity = self.last_mark


def run_backtest(
    candles: Sequence[Candle],
    strategy: Strategy,
    config: BacktestConfig | None = None,
    trade_from: int = 0,
) -> BacktestResult:
    """Simulate a strategy; see the module docstring for fill rules.

    Candles before ``trade_from`` are warm-up only: the strategy sees
    them, but nothing is traded or counted. The decision made on candle
    ``trade_from - 1`` is the first one executed.
    """

    config = config or BacktestConfig()
    candles = list(candles)
    validate_series(candles)

    if type(trade_from) is not int or not 0 <= trade_from <= len(candles) - 2:
        raise ValueError("trade_from must leave at least two traded candles")

    if len(candles) < 2:
        raise ValueError("At least two candles are required")

    sim = _Simulator(candles, config)
    equity_curve: list[tuple[datetime, float]] = []
    target = 0
    # After a stop-out, wait for the strategy to change its mind
    # before re-entering in the same direction.
    blocked_side = 0

    for index, candle in enumerate(candles):
        if index < trade_from:
            target = _decide(strategy, candles, index, config)
            continue

        sim.start_bar(candle)

        # 1. Execute the decision made on the previous candle's close.
        if index > 0:
            if target != blocked_side:
                blocked_side = 0
            desired = target if target != blocked_side else 0

            if desired != sim.side:
                if sim.side != 0:
                    sim.close_position(candle.open_time, candle.open, "signal")
                if desired != 0:
                    sim.open_position(desired, candle)

        # 2. Intrabar stop loss.
        if sim.side != 0:
            side = sim.side
            if sim.check_stop(candle):
                blocked_side = side

        equity = sim.equity(candle.close)
        sim.peak = max(sim.peak, equity)
        sim.last_mark = equity
        equity_curve.append((candle.open_time, equity))

        if equity <= 0:
            break

        # 3. Decide using only data available at this close.
        target = _decide(strategy, candles, index, config)

    last = candles[trade_from + len(equity_curve) - 1]
    if sim.side != 0:
        # Close at the final close so metrics include exit costs.
        sim.close_position(last.open_time + _step(candles), last.close, "end_of_data")
        equity_curve[-1] = (last.open_time, sim.equity(last.close))

    metrics = compute_metrics(
        equity_curve,
        sim.trades,
        _bars_per_year(candles),
        config.initial_equity,
    )
    metrics["rejected_entries"] = sim.rejected_entries
    metrics["risk_gate"] = (
        "enforced" if config.risk_limits is not None
        else "disabled_research_only"
    )

    return BacktestResult(
        trades=sim.trades,
        equity_curve=equity_curve,
        metrics=metrics,
        rejected_entries=sim.rejected_entries,
    )


def _decide(strategy, candles, index, config) -> int:
    """Ask the strategy for a target using candles[:index + 1] only."""
    target = strategy(_History(candles, index + 1))
    if type(target) is not int or target not in (-1, 0, 1):
        raise ValueError("Strategy must return -1, 0 or 1")
    if target < 0 and not config.allow_short:
        return 0
    return target


def _step(candles: Sequence[Candle]) -> timedelta:
    return candles[-1].open_time - candles[-2].open_time


def split_index(length: int, in_sample_pct: float = 70.0) -> int:
    """Index of the first out-of-sample candle."""

    if not 0 < in_sample_pct < 100:
        raise ValueError("In-sample share must be in (0, 100)")
    cut = int(length * in_sample_pct / 100)
    if cut < 2 or length - cut < 2:
        raise ValueError("Not enough candles to split")
    return cut


def split_candles(
    candles: Sequence[Candle], in_sample_pct: float = 70.0
) -> tuple[list[Candle], list[Candle]]:
    """Chronological split for in-sample / out-of-sample evaluation."""

    cut = split_index(len(candles), in_sample_pct)
    return list(candles[:cut]), list(candles[cut:])
