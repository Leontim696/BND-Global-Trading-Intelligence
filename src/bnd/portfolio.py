"""Multi-market portfolio backtester with leverage. Paper research only.

One account trades every market in the universe at once:

1. The strategy gives each market a signal in [-1, 1] (long/flat/short).
2. Volatility sizing: each market starts at signal x target / market vol,
   so a calm market (forex) gets a larger position than a wild one (gas).
   The whole book is then scaled so its volatility, measured from the
   last ``vol_lookback`` dates of real joint returns (correlations
   included), equals the target. Assuming independent markets would
   understate risk badly when they fall together, as in 2011 or 2020.
   ``sizing="equal"`` uses signal / N instead.
3. Leverage: if gross exposure (sum of |weights|) exceeds max_leverage,
   every weight is scaled down proportionally.
4. Decisions use only candles up to each market's close and execute at
   that market's next open, with per-market fees and slippage.
5. Each market pays its annual carry on |notional| (crypto funding;
   futures none). Optional extra financing on gross exposure above
   equity, for margin loans or CFDs. Idle equity may earn interest.
6. Kill switch: once drawdown from peak reaches max_drawdown_pct, every
   position is closed at its next open and trading stops.
"""

from bisect import bisect_right
from collections.abc import Sequence as SequenceABC
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite, log, sqrt
from statistics import stdev
from typing import Callable, Mapping, Sequence

from .backtester import SECONDS_PER_YEAR, compute_metrics
from .market_data import Candle, validate_series
from .universe import Market


@dataclass(frozen=True)
class PortfolioConfig:
    initial_equity: float = 10_000.0
    sizing: str = "volatility"
    target_vol_pct: float = 15.0
    vol_lookback: int = 60
    max_leverage: float = 3.0
    max_weight: float = 1.0
    rebalance_threshold: float = 0.05
    # Extra financing on gross exposure above equity (margin loans, CFDs);
    # futures need only margin, so the default is none.
    financing_pct_annual: float = 0.0
    cash_rate_pct_annual: float = 0.0
    max_drawdown_pct: float | None = 30.0
    allow_short: bool = True
    cost_multiplier: float = 1.0

    def __post_init__(self):
        if self.sizing not in ("volatility", "equal"):
            raise ValueError("Sizing must be 'volatility' or 'equal'")
        checks = (
            (self.initial_equity, 0, None, "Initial equity"),
            (self.target_vol_pct, 0, 200, "Target volatility"),
            (self.max_leverage, 0, 20, "Maximum leverage"),
            (self.max_weight, 0, 20, "Maximum weight"),
            (self.rebalance_threshold, 0, 1, "Rebalance threshold"),
            (self.cost_multiplier, 0, 10, "Cost multiplier"),
        )
        for value, low, high, name in checks:
            if not isfinite(value) or value <= low or (high is not None and value > high):
                raise ValueError(f"{name} out of range")
        for value in (self.financing_pct_annual, self.cash_rate_pct_annual):
            if not isfinite(value) or not 0 <= value <= 100:
                raise ValueError("Annual rates must be in [0, 100] percent")
        if type(self.vol_lookback) is not int or self.vol_lookback < 5:
            raise ValueError("Volatility lookback must be an integer >= 5")
        if self.max_drawdown_pct is not None and not 0 < self.max_drawdown_pct < 100:
            raise ValueError("Maximum drawdown must be in (0, 100) percent")


class _History(SequenceABC):
    """Read-only view of one market's candles up to ``end``."""

    def __init__(self, candles, end):
        self._candles, self._end = candles, end

    def __len__(self):
        return self._end

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self._candles[i] for i in range(*index.indices(self._end))]
        if index < 0:
            index += self._end
        if not 0 <= index < self._end:
            raise IndexError("History index out of range")
        return self._candles[index]


@dataclass
class _Book:
    market: Market
    candles: list
    strategy: Callable
    position: int = -1          # index of the latest candle seen
    quantity: float = 0.0
    price: float = 0.0          # latest mark
    signal: float = 0.0
    vol: float | None = None
    target: float = 0.0         # weight to execute at the next open
    cashflow: float = 0.0       # trade cash flows, for per-market P&L
    fees: float = 0.0
    fills: int = 0
    weight_sum: float = 0.0
    weight_marks: int = 0
    by_time: dict = field(default_factory=dict)
    vols: list = field(default_factory=list)
    returns: dict = field(default_factory=dict)  # time -> log return


def _volatility(candles, end, lookback) -> float | None:
    """Annualised close-to-close volatility from the candles before ``end``."""
    if end <= lookback:
        return None
    window = candles[end - lookback - 1:end]
    returns = [log(b.close / a.close) for a, b in zip(window, window[1:])]
    seconds = (window[-1].open_time - window[0].open_time).total_seconds()
    if seconds <= 0:
        return None
    return stdev(returns) * sqrt(SECONDS_PER_YEAR * lookback / seconds)


def _volatility_by_end(candles, lookback) -> list:
    """``_volatility(candles, end, lookback)`` for every end, in one pass.

    Entry ``end`` uses candles[:end] only. Rolling sums are refreshed
    from scratch every 500 steps to stop rounding drift.
    """
    out = [None] * (len(candles) + 1)
    returns = [log(b.close / a.close) for a, b in zip(candles, candles[1:])]
    total = squares = 0.0
    for end in range(lookback + 1, len(candles) + 1):
        window = returns[end - lookback - 1:end - 1]
        if (end - lookback - 1) % 500 == 0:
            total, squares = sum(window), sum(r * r for r in window)
        else:
            new, old = returns[end - 2], returns[end - lookback - 2]
            total += new - old
            squares += new * new - old * old
        seconds = (candles[end - 1].open_time - candles[end - lookback - 1].open_time).total_seconds()
        variance = (squares - total * total / lookback) / (lookback - 1)
        if seconds > 0:
            out[end] = sqrt(max(variance, 0.0)) * sqrt(SECONDS_PER_YEAR * lookback / seconds)
    return out


def _book_volatility(books, weights, times) -> float | None:
    """Annualised volatility of today's weights over past joint returns.

    Each past date's return is the weighted sum of the markets' actual
    returns that day (0 where a market was closed), so correlations are
    included. None when there is not enough history.
    """
    if len(times) < 5:
        return None
    series = [
        sum(weights[b.market.name] * b.returns.get(t, 0.0) for b in books)
        for t in times
    ]
    seconds = (times[-1] - times[0]).total_seconds()
    deviation = stdev(series)
    if seconds <= 0 or deviation <= 0:
        return None
    return deviation * sqrt((len(times) - 1) * SECONDS_PER_YEAR / seconds)


def target_weights(books, config: PortfolioConfig, recent_times) -> dict:
    """Weights to hold from each book's ``signal`` and ``vol`` (step 2-3).

    ``recent_times`` are the last ``vol_lookback`` dates seen, used to
    measure the book's joint volatility. Books without a volatility
    estimate get no weight. Shared by the backtest and the paper runner.
    """
    ready = [b for b in books if b.vol is not None and b.vol > 0]
    if config.sizing == "equal":
        raw = {b.market.name: b.signal / len(books) for b in ready}
    else:
        raw = {b.market.name: b.signal * config.target_vol_pct / 100 / b.vol
               for b in ready}
        measured = _book_volatility(ready, raw, recent_times)
        factor = (config.target_vol_pct / 100 / measured) if measured else 0.0
        raw = {name: weight * factor for name, weight in raw.items()}
    weights = {name: max(-config.max_weight, min(config.max_weight, weight))
               for name, weight in raw.items()}
    gross = sum(abs(w) for w in weights.values())
    scale = config.max_leverage / gross if gross > config.max_leverage else 1.0
    return {name: weight * scale for name, weight in weights.items()}


def strategy_for(factory, market):
    """A new strategy for ``market``.

    Factories marked ``per_market = True`` receive the market, so a
    cross-sectional strategy can look up its own row in a shared ranking.
    """
    return factory(market) if getattr(factory, "per_market", False) else factory()


def run_portfolio(
    data: Mapping[str, Sequence[Candle]],
    markets: Sequence[Market],
    factory: Callable[[], Callable],
    config: PortfolioConfig | None = None,
    trade_from: datetime | None = None,
) -> dict:
    """Simulate one account across ``markets``.

    Candles before ``trade_from`` are warm-up: strategies and volatility
    estimates see them, but nothing is traded or counted.
    """

    config = config or PortfolioConfig()
    if not markets:
        raise ValueError("At least one market is required")
    books = []
    for market in markets:
        candles = list(data.get(market.name, ()))
        if len(candles) < 2:
            raise ValueError(f"Not enough candles for {market.name}")
        validate_series(candles)
        book = _Book(market, candles, strategy_for(factory, market))
        book.by_time = {c.open_time: i for i, c in enumerate(candles)}
        book.vols = _volatility_by_end(candles, config.vol_lookback)
        book.returns = {
            b.open_time: log(b.close / a.close) for a, b in zip(candles, candles[1:])
        }
        books.append(book)

    times = sorted({c.open_time for book in books for c in book.candles})
    if trade_from is not None and not times[0] < trade_from <= times[-2]:
        raise ValueError("trade_from must leave at least two traded dates")

    cash = config.initial_equity
    curve: list[tuple[datetime, float]] = []
    totals = {"fees": 0.0, "financing": 0.0, "interest": 0.0, "fills": 0, "traded": 0.0}
    gross_marks: list[float] = []
    peak = config.initial_equity
    halted_at = None
    previous_time = None
    started = trade_from is None
    seen: list[datetime] = []

    def equity() -> float:
        return cash + sum(b.quantity * b.price for b in books)

    def trade(book, price_raw, weight, total_equity):
        nonlocal cash
        wanted = weight * total_equity / price_raw
        delta = wanted - book.quantity
        if delta == 0:
            return
        slip = book.market.slippage_pct * config.cost_multiplier / 100
        fee_rate = book.market.fee_pct * config.cost_multiplier / 100
        price = price_raw * (1 + slip) if delta > 0 else price_raw * (1 - slip)
        fee = abs(delta) * price * fee_rate
        totals["traded"] += abs(delta) * price
        cash -= delta * price + fee
        book.cashflow -= delta * price + fee
        book.quantity = wanted
        book.fees += fee
        book.fills += 1
        totals["fees"] += fee
        totals["fills"] += 1

    for time in times:
        if not started and time >= trade_from:
            started = True
        today = [b for b in books if time in b.by_time]
        seen.append(time)

        # 1. Opens: mark, then execute the targets decided at the last close.
        for book in today:
            book.position = book.by_time[time]
            book.price = book.candles[book.position].open
        if started and equity() > 0:
            total = equity()
            for book in today:
                weight = 0.0 if halted_at else book.target
                current = book.quantity * book.price / total
                flips = (weight > 0) != (current > 0) or (weight < 0) != (current < 0)
                if (flips and (weight or current)) or abs(weight - current) >= config.rebalance_threshold:
                    trade(book, book.price, weight, total)

        # 2. Closes.
        for book in today:
            book.price = book.candles[book.position].close

        # 3. Carry for the calendar time since the previous date.
        # Nothing accrues for the warm-up gap before the first traded date.
        if started and curve:
            years = (time - previous_time).total_seconds() / SECONDS_PER_YEAR
            total = equity()
            gross = sum(abs(b.quantity * b.price) for b in books)
            financing = max(0.0, gross - total) * config.financing_pct_annual / 100 * years
            financing += sum(
                abs(b.quantity * b.price) * b.market.carry_pct_annual / 100 for b in books
            ) * config.cost_multiplier * years
            interest = max(0.0, total - gross) * config.cash_rate_pct_annual / 100 * years
            cash += interest - financing
            totals["financing"] += financing
            totals["interest"] += interest
        previous_time = time

        # 4. Mark the account; the kill switch is the deterministic veto.
        if started:
            total = equity()
            curve.append((time, total))
            gross = sum(abs(b.quantity * b.price) for b in books)
            gross_marks.append(gross / total if total > 0 else 0.0)
            for book in books:
                if total > 0:
                    book.weight_sum += abs(book.quantity * book.price) / total
                    book.weight_marks += 1
            peak = max(peak, total)
            if total <= 0:
                break
            if (config.max_drawdown_pct is not None and not halted_at
                    and 100 * (peak - total) / peak >= config.max_drawdown_pct):
                halted_at = time

        # 5. Decide at the close using only candles seen so far.
        for book in today:
            end = book.position + 1
            signal = book.strategy(_History(book.candles, end))
            if (isinstance(signal, bool) or not isinstance(signal, (int, float))
                    or not isfinite(signal) or not -1 <= signal <= 1):
                raise ValueError("Strategy must return a number in [-1, 1]")
            book.signal = signal if (signal >= 0 or config.allow_short) else 0.0
            book.vol = book.vols[end]

        weights = target_weights(books, config, seen[-config.vol_lookback:])
        for book in books:
            book.target = weights.get(book.market.name, 0.0)

    # Close everything at the final marks, paying exit costs.
    final_time = curve[-1][0] if curve else times[-1]
    if curve and curve[-1][1] > 0:
        total = equity()
        for book in books:
            if book.quantity:
                trade(book, book.price, 0.0, total)
        curve[-1] = (final_time, equity())

    if len(curve) < 2:
        raise ValueError("Not enough traded dates")
    span = (curve[-1][0] - curve[0][0]).total_seconds()
    periods = (len(curve) - 1) * SECONDS_PER_YEAR / span if span > 0 else 0.0
    metrics = compute_metrics(curve, [], periods, config.initial_equity,
                              traded_notional=totals["traded"])
    for key in ("trades", "win_rate_pct", "profit_factor", "expectancy"):
        metrics.pop(key, None)
    metrics.update({
        "fills": totals["fills"],
        "total_fees": totals["fees"],
        "total_financing": totals["financing"],
        "total_interest": totals["interest"],
        "avg_gross_leverage": sum(gross_marks) / len(gross_marks) if gross_marks else 0.0,
        "max_gross_leverage": max(gross_marks, default=0.0),
        "kill_switch_at": halted_at.isoformat() if halted_at else None,
        "markets": len(books),
    })
    per_market = [
        {
            "market": b.market.name,
            "asset_class": b.market.asset_class,
            "pnl": b.cashflow + b.quantity * b.price,
            "fees": b.fees,
            "fills": b.fills,
            "avg_abs_weight": b.weight_sum / b.weight_marks if b.weight_marks else 0.0,
        }
        for b in books
    ]
    per_market.sort(key=lambda row: row["pnl"], reverse=True)
    return {"metrics": metrics, "per_market": per_market, "equity_curve": curve}


def in_currency(curve, usd_per_unit: Sequence[Candle]) -> list:
    """A USD equity curve seen by an investor whose money is in another currency.

    ``usd_per_unit`` is that currency's USD price (EURUSD for EUR). Unhedged:
    the investor converts at the start and back at each date, so a falling
    dollar lowers the result. Each date uses the latest close at or before it.
    """
    times = [c.open_time for c in usd_per_unit]
    out = []
    for time, equity in curve:
        index = bisect_right(times, time) - 1
        if index < 0:
            raise ValueError(f"No exchange rate on or before {time.date()}")
        out.append((time, equity / usd_per_unit[index].close))
    return out


def currency_metrics(curve, usd_per_unit: Sequence[Candle],
                     initial_equity: float | None = None) -> dict:
    """Return and risk of an equity curve after conversion (see ``in_currency``).

    ``initial_equity`` (USD) is converted at the first date's rate;
    by default the first point of the curve is the start.
    """
    converted = in_currency(curve, usd_per_unit)
    if len(converted) < 2:
        raise ValueError("Not enough dates to convert")
    start = converted[0][1] if initial_equity is None else \
        initial_equity * converted[0][1] / curve[0][1]
    span = (converted[-1][0] - converted[0][0]).total_seconds()
    periods = (len(converted) - 1) * SECONDS_PER_YEAR / span if span > 0 else 0.0
    metrics = compute_metrics(converted, [], periods, start)
    keys = ("total_return_pct", "cagr_pct", "sharpe", "sortino", "volatility_pct",
            "max_drawdown_pct")
    return {key: metrics.get(key) for key in keys}


def record_signals(data, markets, factory, config=None, trade_from=None):
    """Run the portfolio and keep every market's signal per candle index."""
    signals = {}
    order = iter(markets)

    def recording_factory():
        market = next(order)
        strategy, record = strategy_for(factory, market), []
        signals[market.name] = record

        def wrapped(history):
            value = strategy(history)
            record.append(value)
            return value

        return wrapped

    return run_portfolio(data, markets, recording_factory, config, trade_from), signals


_WORKER: dict = {}


def _init_worker(data, markets, config, trade_from):
    _WORKER["context"] = (data, markets, config, trade_from)


def _replay_in_worker(sequences):
    return _replay_sharpe(sequences, *_WORKER["context"])


def _replay_sharpe(sequences, data, markets, config, trade_from):
    """Portfolio Sharpe for fixed per-market signal sequences."""
    order = iter(markets)

    def factory():
        sequence = sequences[next(order).name]
        return lambda history: sequence[min(len(history), len(sequence)) - 1]

    sharpe = run_portfolio(data, markets, factory, config, trade_from)["metrics"]["sharpe"]
    return sharpe if sharpe is not None else float("-inf")


def portfolio_permutation_test(data, markets, signals, config=None, trade_from=None,
                               permutations=100, seed=7, workers=1) -> dict:
    """Does the strategy's timing matter, or only diversification and leverage?

    Each market keeps its own positions and holding periods, but their
    timing is shuffled (``robustness.permute_runs``) from the first traded
    candle on. The portfolio is rebuilt with the same sizing and leverage.
    p_value is the share of shuffles with a Sharpe at least as high. A
    strategy whose signal never changes (always long) has nothing to
    shuffle, so it gets p = 1: its result is diversification and leverage.
    Shuffles are drawn up front from ``seed``, so results do not depend
    on ``workers``.
    """
    import random
    from concurrent.futures import ProcessPoolExecutor

    from .robustness import permute_runs

    if permutations < 1:
        raise ValueError("At least one permutation is required")

    starts = {}
    for market in markets:
        candles = data[market.name]
        first = next((i for i, c in enumerate(candles)
                      if trade_from is None or c.open_time >= trade_from), len(candles))
        starts[market.name] = max(first - 1, 0)

    rng = random.Random(seed)
    shuffles = [{name: permute_runs(signals[name], rng, starts[name]) for name in signals}
                for _ in range(permutations)]
    actual = _replay_sharpe(signals, data, markets, config, trade_from)
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker,
                                 initargs=(data, markets, config, trade_from)) as pool:
            shuffled = list(pool.map(_replay_in_worker, shuffles))
    else:
        shuffled = [_replay_sharpe(seq, data, markets, config, trade_from) for seq in shuffles]
    shuffled.sort()
    at_least = sum(value >= actual - 1e-12 for value in shuffled)
    return {
        "actual_sharpe": actual,
        "shuffled_median_sharpe": shuffled[len(shuffled) // 2],
        "shuffled_p95_sharpe": shuffled[min(len(shuffled) - 1, int(0.95 * len(shuffled)))],
        "permutations": permutations,
        "seed": seed,
        "p_value": (at_least + 1) / (permutations + 1),
    }
