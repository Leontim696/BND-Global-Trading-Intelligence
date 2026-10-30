"""Robustness checks: is a backtest result an edge or luck?

- parameter_grid: every parameter combination, so a single lucky
  setting stands out against its neighbours.
- select_in_sample: choose parameters on in-sample data only, then
  report how that choice ranks out-of-sample.
- permutation_test: keep the strategy's own positions and holding
  periods but shuffle their order in time. If the real timing does not
  clearly beat the shuffled timings, the result is indistinguishable
  from luck.
- cost_stress: rerun with fees and slippage multiplied.

All checks use the same backtester, fills and costs as `run`.
"""

import random
from decimal import Decimal, InvalidOperation
from math import isfinite
from dataclasses import replace
from itertools import groupby, product
from statistics import median
from typing import Callable, Sequence

from .backtester import BacktestConfig, run_backtest
from .market_data import Candle

StrategyFactory = Callable[..., Callable]


def parse_value(text: str):
    """Parse a parameter value: int, float or true/false."""

    lowered = text.strip().lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(lowered)
    except ValueError:
        pass
    try:
        value = float(lowered)
    except ValueError as exc:
        raise ValueError(f"Invalid parameter value: {text!r}") from exc
    if not isfinite(value):
        raise ValueError(f"Invalid parameter value: {text!r}")
    return value


def parse_range(text: str) -> list:
    """Parse 'start:stop:step' (inclusive) or a single number.

    Integers stay integers; any decimal makes every value a float,
    computed with Decimal so 1.5:3:0.5 gives exactly 1.5, 2.0, 2.5, 3.0.
    """

    parts = text.split(":")
    try:
        numbers = [Decimal(part.strip()) for part in parts]
    except InvalidOperation as exc:
        raise ValueError("Range must be start:stop:step numbers") from exc
    if any(not number.is_finite() for number in numbers):
        raise ValueError("Range must be start:stop:step numbers")

    integral = all(number == number.to_integral_value() and "." not in part
                   for number, part in zip(numbers, parts))

    def convert(number):
        return int(number) if integral else float(number)

    if len(numbers) == 1:
        return [convert(numbers[0])]
    if len(numbers) != 3 or numbers[2] <= 0 or numbers[1] < numbers[0]:
        raise ValueError("Range must be start:stop:step with step > 0")

    start, stop, step = numbers
    values = []
    while start <= stop:
        values.append(convert(start))
        start += step
    return values


def parameter_sets(**ranges: list[int]) -> list[dict]:
    names = list(ranges)
    return [dict(zip(names, combo)) for combo in product(*ranges.values())]


def _metrics(result) -> dict:
    keys = ("total_return_pct", "sharpe", "max_drawdown_pct", "trades",
            "time_in_market_pct", "avg_capital_exposure_pct")
    return {key: result.metrics[key] for key in keys}


def parameter_grid(
    candles: Sequence[Candle],
    factory: StrategyFactory,
    params: Sequence[dict],
    config: BacktestConfig,
    trade_from: int = 0,
) -> list[dict]:
    """Backtest every valid parameter set; invalid sets are skipped."""

    rows = []
    for values in params:
        try:
            strategy = factory(**values)
        except ValueError:
            continue
        result = run_backtest(candles, strategy, config, trade_from)
        rows.append({"params": values, **_metrics(result)})

    if not rows:
        raise ValueError("No valid parameter combination")
    return rows


def summarize_grid(rows: Sequence[dict], benchmark_return_pct: float) -> dict:
    returns = [row["total_return_pct"] for row in rows]
    best = max(rows, key=lambda row: row["total_return_pct"])
    return {
        "combinations": len(rows),
        "beat_buy_and_hold": sum(r > benchmark_return_pct for r in returns),
        "beat_buy_and_hold_pct": 100 * sum(
            r > benchmark_return_pct for r in returns
        ) / len(rows),
        "profitable": sum(r > 0 for r in returns),
        "median_return_pct": median(returns),
        "best": best,
        "buy_and_hold_return_pct": benchmark_return_pct,
    }


def select_in_sample(
    in_sample_rows: Sequence[dict], out_of_sample_rows: Sequence[dict]
) -> dict:
    """Pick the best in-sample Sharpe and locate it out-of-sample."""

    def score(row):
        return row["sharpe"] if row["sharpe"] is not None else float("-inf")

    chosen = max(in_sample_rows, key=score)
    ranked = sorted(out_of_sample_rows, key=score, reverse=True)
    oos = next(row for row in ranked if row["params"] == chosen["params"])

    return {
        "params": chosen["params"],
        "in_sample": {k: v for k, v in chosen.items() if k != "params"},
        "out_of_sample": {k: v for k, v in oos.items() if k != "params"},
        "out_of_sample_rank": ranked.index(oos) + 1,
        "out_of_sample_combinations": len(ranked),
    }


def record_targets(
    candles: Sequence[Candle],
    strategy: Callable,
    config: BacktestConfig,
    trade_from: int = 0,
):
    """Run a backtest and capture the target returned on every candle."""

    targets: list[int] = []

    def recording(history):
        target = strategy(history)
        targets.append(target)
        return target

    result = run_backtest(candles, recording, config, trade_from)
    return result, targets


def permute_runs(targets: Sequence[int], rng: random.Random, start: int = 0) -> list[int]:
    """Shuffle when positions happen after ``start``, not what they are.

    The sequence of run values (e.g. flat, long, flat, long) is kept and
    run lengths are shuffled among runs of the same value. Adjacent runs
    therefore never merge: the number of trades, the set of holding
    periods and total exposure are unchanged; only their timing moves.
    """

    head = list(targets[:start])
    runs = [(value, len(list(group))) for value, group in groupby(targets[start:])]
    lengths: dict[int, list[int]] = {}
    for value, length in runs:
        lengths.setdefault(value, []).append(length)
    for pool in lengths.values():
        rng.shuffle(pool)
    body = []
    for value, _ in runs:
        body.extend([value] * lengths[value].pop())
    return head + body


def permutation_test(
    candles: Sequence[Candle],
    targets: Sequence[int],
    config: BacktestConfig,
    trade_from: int = 0,
    permutations: int = 200,
    seed: int = 7,
) -> dict:
    """Compare real timing with shuffled timings of the same positions."""

    if permutations < 1:
        raise ValueError("At least one permutation is required")

    def replay(sequence):
        # A wiped-out run stops early, so its sequence can be short.
        return run_backtest(
            candles,
            lambda history: sequence[min(len(history), len(sequence)) - 1],
            config,
            trade_from,
        ).metrics["total_return_pct"]

    actual = replay(list(targets))
    rng = random.Random(seed)
    # Decisions from candle trade_from - 1 onward are executed.
    start = max(trade_from - 1, 0)
    shuffled = sorted(
        replay(permute_runs(targets, rng, start)) for _ in range(permutations)
    )
    at_least_as_good = sum(value >= actual for value in shuffled)

    def percentile(p):
        return shuffled[min(len(shuffled) - 1, int(p / 100 * len(shuffled)))]

    return {
        "actual_return_pct": actual,
        "permutations": permutations,
        "seed": seed,
        "shuffled_median_return_pct": median(shuffled),
        "shuffled_p5_return_pct": percentile(5),
        "shuffled_p95_return_pct": percentile(95),
        # One-sided; +1 counts the real ordering as one of the outcomes.
        "p_value": (at_least_as_good + 1) / (permutations + 1),
    }


def cost_stress(
    candles: Sequence[Candle],
    make_strategy: Callable[[], Callable],
    config: BacktestConfig,
    multipliers: Sequence[float] = (1.0, 2.0, 3.0),
    trade_from: int = 0,
) -> list[dict]:
    rows = []
    for multiplier in multipliers:
        # Stress every cost, but not the interest earned on idle cash.
        costs = replace(
            config.costs,
            fee_pct=config.costs.fee_pct * multiplier,
            slippage_pct=config.costs.slippage_pct * multiplier,
            funding_pct_annual=min(100.0, config.costs.funding_pct_annual * multiplier),
        )
        result = run_backtest(
            candles,
            make_strategy(),
            replace(config, costs=costs),
            trade_from,
        )
        rows.append({
            "cost_multiplier": multiplier,
            "fee_pct": costs.fee_pct,
            "slippage_pct": costs.slippage_pct,
            **_metrics(result),
        })
    return rows


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, in the input order.

    Testing many strategies at once makes a lucky p < 0.05 likely; the
    adjustment keeps the chance of any false discovery at the threshold.
    """

    count = len(p_values)
    order = sorted(range(count), key=lambda i: p_values[i])
    adjusted = [0.0] * count
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (count - rank) * p_values[index]))
        adjusted[index] = running
    return adjusted
