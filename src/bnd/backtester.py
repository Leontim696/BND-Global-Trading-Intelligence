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

# Target exposure in [-1, 1] as a fraction of the allocation:
# 1 = fully long, 0 = flat, -1 = fully short, 0.6 = 60% long.
Strategy = Callable[[Sequence[Candle]], float]

SECONDS_PER_YEAR = 365.25 * 24 * 3600


@dataclass(frozen=True)
class CostModel:
    """Percent costs per fill, plus annual carry while a position is open.

    funding_pct_annual: charged on open position notional, long or short
        (perpetual-futures funding or borrow; conservative: both sides pay).
    cash_rate_pct_annual: interest earned on equity not invested.
    """

    fee_pct: float = 0.10
    slippage_pct: float = 0.05
    funding_pct_annual: float = 0.0
    cash_rate_pct_annual: float = 0.0

    def __post_init__(self):
        for value in (self.fee_pct, self.slippage_pct):
            if not isfinite(value) or not 0 <= value < 10:
                raise ValueError("Costs must be in [0, 10) percent")
        for value in (self.funding_pct_annual, self.cash_rate_pct_annual):
            if not isfinite(value) or not 0 <= value <= 100:
                raise ValueError("Annual rates must be in [0, 100] percent")


@dataclass(frozen=True)
class BacktestConfig:
    initial_equity: float = 10_000.0
    costs: CostModel = field(default_factory=CostModel)
    # Percent of equity requested per entry, before risk checks. Above
    # 100 is leverage (e.g. 300 = 3x); losses scale the same way.
    allocation_pct: float = 100.0
    # Optional protective stop; also used by the risk engine for sizing.
    stop_loss_pct: float | None = None
    allow_short: bool = False
    risk_limits: RiskLimits | None = None
    # Resize an open position only when the target exposure moves by at
    # least this fraction of the allocation, to limit fee churn.
    rebalance_threshold: float = 0.10

    def __post_init__(self):
        if not isfinite(self.initial_equity) or self.initial_equity <= 0:
            raise ValueError("Initial equity must be positive")

        if not isfinite(self.allocation_pct) or not 0 < self.allocation_pct <= 1000:
            raise ValueError("Allocation must be in (0, 1000] percent (max 10x leverage)")

        if self.stop_loss_pct is not None and (
            not isfinite(self.stop_loss_pct)
            or not 0 < self.stop_loss_pct < 100
        ):
            raise ValueError("Stop loss must be in (0, 100) percent")

        if not isfinite(self.rebalance_threshold) or not 0 < self.rebalance_threshold <= 1:
            raise ValueError("Rebalance threshold must be in (0, 1]")

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


def bars_per_year(candles: Sequence[Candle]) -> float:
    """Observed candles per year: count over elapsed time.

    Using the typical spacing would assume trading every day; markets
    closed at weekends (forex, stocks, futures) have about 252 daily
    candles a year, not 365, which would overstate Sharpe and miscount
    years.
    """
    if len(candles) < 2:
        return 0.0
    seconds = (candles[-1].open_time - candles[0].open_time).total_seconds()
    return (len(candles) - 1) * SECONDS_PER_YEAR / seconds


def compute_metrics(
    equity_curve: Sequence[tuple[datetime, float]],
    trades: Sequence[Trade],
    bars_per_year: float,
    initial_equity: float,
    risk_free_rate_annual: float = 0.0,
    traded_notional: float | None = None,
) -> dict:
    """Profit and risk metrics, evaluated as two separate objectives:
    absolute net profit and risk-adjusted return.

    traded_notional: total |value| of every fill, for turnover
    (traded value per year, in multiples of average equity).
    """
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
    sharpe = sortino = volatility = None
    if len(returns) >= 2 and bars_per_year > 0:
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        rf = (1 + risk_free_rate_annual) ** (1 / bars_per_year) - 1
        volatility = sqrt(variance) * sqrt(bars_per_year)
        if variance > 0:
            sharpe = (mean - rf) / sqrt(variance) * sqrt(bars_per_year)
        # Downside deviation below the risk-free rate, over all periods.
        downside = sum(min(0.0, r - rf) ** 2 for r in returns) / len(returns)
        if downside > 0:
            sortino = (mean - rf) / sqrt(downside) * sqrt(bars_per_year)

    years = len(equities) / bars_per_year if bars_per_year > 0 else 0
    cagr = None
    if years > 0 and final > 0:
        cagr = (final / initial_equity) ** (1 / years) - 1

    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [t.pnl for t in trades if t.pnl <= 0]
    gross_loss = -sum(losses)
    calmar = (
        cagr / max_drawdown if cagr is not None and max_drawdown > 0 else None
    )
    average_equity = sum(equities) / len(equities) if equities else initial_equity
    turnover = (
        traded_notional / average_equity / years
        if traded_notional is not None and years > 0 and average_equity > 0
        else None
    )

    return {
        "initial_equity": initial_equity,
        "final_equity": final,
        "net_profit": final - initial_equity,
        "total_return_pct": 100 * (final / initial_equity - 1),
        "cagr_pct": None if cagr is None else 100 * cagr,
        "max_drawdown_pct": 100 * max_drawdown,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "volatility_pct": None if volatility is None else 100 * volatility,
        "turnover": turnover,
        "trades": len(trades),
        "win_rate_pct": 100 * len(wins) / len(trades) if trades else None,
        "profit_factor": sum(wins) / gross_loss if gross_loss > 0 else None,
        # Average net profit per closed trade, in account currency.
        "expectancy": sum(t.pnl for t in trades) / len(trades) if trades else None,
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
        # Requested exposure of the open position (fraction of allocation).
        self.size = 0.0
        self.trade_start_cash = 0.0
        self.trade_fees = 0.0
        self.max_quantity = 0.0
        self.entry_time: datetime | None = None
        self.entry_price = 0.0
        self.stop_price: float | None = None
        self.trades: list[Trade] = []
        self.rejected_entries = 0
        self.total_funding = 0.0
        self.total_interest = 0.0
        self.traded_notional = 0.0
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

    def _approve(self, equity: float, notional: float, held: float) -> float | None:
        """Risk-approved additional notional, or None when vetoed."""
        if self.config.risk_limits is None:
            return notional
        risk = evaluate_risk(
            Portfolio(
                equity=equity,
                daily_loss=max(0.0, self.day_start_equity - equity),
                drawdown=max(0.0, self.peak - equity),
                gross_exposure=held,
            ),
            TradeProposal(
                notional=notional,
                stop_loss_pct=self.config.stop_loss_pct,
                # Requested position size relative to equity.
                leverage=max(1.0, (held + notional) / equity),
            ),
            self.config.risk_limits,
        )
        if risk.decision == RiskDecision.REJECT:
            self.rejected_entries += 1
            return None
        return risk.approved_notional

    def _add(self, notional: float, candle: Candle) -> None:
        """Buy (long) or sell short ``notional`` more at the open."""
        side = self.side
        price = self._fill(candle.open, side)
        # Keep the fee inside the approved notional.
        added = notional / (price * (1 + self.config.costs.fee_pct / 100))
        fee = self._fee(added * price)
        self.traded_notional += added * price
        held = abs(self.quantity)

        self.entry_price = (held * self.entry_price + added * price) / (held + added)
        self.quantity += side * added
        self.cash -= side * added * price + fee
        self.trade_fees += fee
        self.max_quantity = max(self.max_quantity, abs(self.quantity))

        if self.config.stop_loss_pct is not None:
            distance = self.config.stop_loss_pct / 100
            self.stop_price = self.entry_price * (1 - side * distance)

    def open_position(self, side: int, candle: Candle, size: float = 1.0) -> None:
        equity = self.equity(candle.open)
        if equity <= 0:
            # Account wiped out (e.g. a short gapped through its stop).
            self.rejected_entries += 1
            return
        notional = self._approve(
            equity, equity * self.config.allocation_pct / 100 * size, 0.0
        )
        if notional is None:
            return

        self.trade_start_cash = self.cash
        self.trade_fees = 0.0
        self.max_quantity = 0.0
        self.quantity = 0.0
        self.entry_price = 0.0
        self.side = side
        self.size = size
        self.entry_time = candle.open_time
        self._add(notional, candle)

    def resize_position(self, size: float, candle: Candle) -> None:
        """Move an open position toward ``size`` of the allocation."""
        equity = self.equity(candle.open)
        if equity <= 0:
            return
        held = abs(self.quantity) * candle.open
        wanted = equity * self.config.allocation_pct / 100 * size
        change = wanted - held

        if change > 0:
            # Approve the whole resulting position, so repeated small
            # increases cannot add up past the per-trade risk limit.
            approved = self._approve(equity, wanted, 0.0)
            if approved is None:
                return
            change = min(change, approved - held)
            if change > 0:
                self._add(change, candle)
        elif change < 0:
            removed = min(-change / candle.open, abs(self.quantity))
            price = self._fill(candle.open, -self.side)
            fee = self._fee(removed * price)
            self.traded_notional += removed * price
            self.quantity -= self.side * removed
            self.cash += self.side * removed * price - fee
            self.trade_fees += fee

        self.size = size

    def close_position(self, time: datetime, raw_price: float, reason: str) -> None:
        price = self._fill(raw_price, -self.side)
        fee = self._fee(self.quantity * price)
        self.traded_notional += abs(self.quantity) * price
        self.cash += self.quantity * price - fee
        self.trade_fees += fee

        # Flat before and after, so the cash change is the exact P&L,
        # including every resize and fee.
        self.trades.append(Trade(
            side=self.side,
            entry_time=self.entry_time,
            entry_price=self.entry_price,
            exit_time=time,
            exit_price=price,
            quantity=self.max_quantity,
            pnl=self.cash - self.trade_start_cash,
            fees=self.trade_fees,
            exit_reason=reason,
        ))

        self.quantity = 0.0
        self.side = 0
        self.size = 0.0
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

    def accrue(self, price: float, years: float) -> None:
        """Charge funding on the position and pay interest on idle equity."""
        costs = self.config.costs
        held = abs(self.quantity) * price
        idle = max(0.0, self.equity(price) - held)
        funding = held * costs.funding_pct_annual / 100 * years
        interest = idle * costs.cash_rate_pct_annual / 100 * years
        self.cash += interest - funding
        self.total_funding += funding
        self.total_interest += interest

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
    bars_in_market = 0
    capital_exposure = 0.0
    years_per_bar = 1 / bars_per_year(candles)

    for index, candle in enumerate(candles):
        if index < trade_from:
            target = _decide(strategy, candles, index, config)
            continue

        sim.start_bar(candle)

        # 1. Execute the decision made on the previous candle's close.
        if index > 0:
            target_side = _sign(target)
            if target_side != blocked_side:
                blocked_side = 0
            desired_side = target_side if target_side != blocked_side else 0
            desired_size = abs(target) if desired_side else 0.0

            if desired_side != sim.side:
                if sim.side != 0:
                    sim.close_position(candle.open_time, candle.open, "signal")
                if desired_side != 0:
                    sim.open_position(desired_side, candle, desired_size)
            elif (sim.side != 0 and abs(desired_size - sim.size)
                  >= config.rebalance_threshold - 1e-12):
                sim.resize_position(desired_size, candle)

        # 2. Intrabar stop loss.
        if sim.side != 0:
            side = sim.side
            if sim.check_stop(candle):
                blocked_side = side

        # 3. Carry for this candle, at its close.
        sim.accrue(candle.close, years_per_bar)

        equity = sim.equity(candle.close)
        sim.peak = max(sim.peak, equity)
        sim.last_mark = equity
        equity_curve.append((candle.open_time, equity))

        if sim.side != 0:
            bars_in_market += 1
            if equity > 0:
                capital_exposure += abs(sim.quantity * candle.close) / equity

        if equity <= 0:
            break

        # 4. Decide using only data available at this close.
        target = _decide(strategy, candles, index, config)

    last = candles[trade_from + len(equity_curve) - 1]
    if sim.side != 0:
        # Close at the final close so metrics include exit costs.
        sim.close_position(last.open_time + _step(candles), last.close, "end_of_data")
        equity_curve[-1] = (last.open_time, sim.equity(last.close))

    metrics = compute_metrics(
        equity_curve,
        sim.trades,
        bars_per_year(candles),
        config.initial_equity,
        traded_notional=sim.traded_notional,
    )
    metrics["rejected_entries"] = sim.rejected_entries
    metrics["total_funding"] = sim.total_funding
    metrics["total_interest"] = sim.total_interest
    # Low exposure makes "beats buy-and-hold" in a falling market cheap.
    metrics["time_in_market_pct"] = 100 * bars_in_market / len(equity_curve)
    metrics["avg_capital_exposure_pct"] = (
        100 * capital_exposure / len(equity_curve)
    )
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


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def _decide(strategy, candles, index, config) -> float:
    """Ask the strategy for a target using candles[:index + 1] only."""
    target = strategy(_History(candles, index + 1))
    if (
        isinstance(target, bool)
        or not isinstance(target, (int, float))
        or not isfinite(target)
        or not -1 <= target <= 1
    ):
        raise ValueError("Strategy must return a number in [-1, 1]")
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
