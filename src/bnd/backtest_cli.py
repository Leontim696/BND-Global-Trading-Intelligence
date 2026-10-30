"""Command line for downloading data and running backtests.

    python -m src.bnd.backtest_cli fetch --symbol BTCUSDT --interval 4h \\
        --start 2019-01-01 --out data/BTCUSDT-4h.csv
    python -m src.bnd.backtest_cli run --data data/BTCUSDT-4h.csv \\
        --strategy sma_crossover --fast 20 --slow 50 --stop-loss 5

Every run is compared with buy-and-hold under the same costs and
reported separately for the in-sample and out-of-sample periods.
"""

import argparse
import json
import sys
from datetime import datetime, timezone

from .backtester import (
    BacktestConfig,
    CostModel,
    bars_per_year,
    run_backtest,
    split_index,
)
from .market_data import (
    MarketDataError,
    fetch_binance_klines,
    find_gaps,
    load_csv,
    save_csv,
    to_bars,
)
from .quant_backtest import BacktestConfig as QuantConfig
from .quant_report import evaluate_sma_report
from .risk_engine import RiskLimits
from .strategies import STRATEGIES, buy_and_hold

SUMMARY_KEYS = (
    "total_return_pct",
    "cagr_pct",
    "max_drawdown_pct",
    "sharpe",
    "trades",
    "win_rate_pct",
    "profit_factor",
    "total_fees",
    "rejected_entries",
    "risk_gate",
)


def _utc_date(text: str) -> datetime:
    value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _make_strategy(args):
    factory = STRATEGIES[args.strategy]
    if args.strategy == "sma_crossover":
        return factory(fast=args.fast, slow=args.slow)
    if args.strategy == "donchian_breakout":
        return factory(entry=args.entry, exit=args.exit)
    return factory()


def _summary(result) -> dict:
    return {
        key: (round(value, 4) if isinstance(value, float) else value)
        for key, value in result.metrics.items()
        if key in SUMMARY_KEYS
    }


def command_fetch(args) -> int:
    end = _utc_date(args.end) if args.end else datetime.now(timezone.utc)
    candles = fetch_binance_klines(
        args.symbol, args.interval, _utc_date(args.start), end
    )
    save_csv(candles, args.out)
    print(
        f"Saved {len(candles)} candles to {args.out} "
        f"({candles[0].open_time.isoformat()} .. "
        f"{candles[-1].open_time.isoformat()})"
    )
    return 0


def command_run(args) -> int:
    candles = load_csv(args.data)
    gaps = find_gaps(candles)
    if gaps and args.require_continuous:
        raise MarketDataError(
            f"{len(gaps)} gaps in data; first after "
            + gaps[0][0].isoformat()
        )

    # Fail closed: running without the risk engine must be explicit.
    if args.risk_per_trade is None and not args.no_risk_gate:
        raise ValueError(
            "Pass --risk-per-trade with --stop-loss, or --no-risk-gate "
            "for an explicitly research-only run"
        )

    risk_limits = None
    if args.risk_per_trade is not None:
        risk_limits = RiskLimits(
            max_risk_per_trade_pct=args.risk_per_trade,
            max_daily_loss_pct=args.max_daily_loss,
            max_drawdown_pct=args.max_drawdown,
            max_gross_exposure_pct=100.0,
            max_leverage=1.0,
        )

    config = BacktestConfig(
        initial_equity=args.equity,
        costs=CostModel(fee_pct=args.fee, slippage_pct=args.slippage),
        allocation_pct=args.allocation,
        stop_loss_pct=args.stop_loss,
        allow_short=args.allow_short,
        risk_limits=risk_limits,
    )
    benchmark_config = BacktestConfig(
        initial_equity=args.equity, costs=config.costs
    )

    # (candles, first traded index). Out-of-sample trading starts at the
    # split, but strategies warm up on the preceding in-sample candles.
    periods = {"full": (candles, 0)}
    if args.in_sample is not None:
        cut = split_index(len(candles), args.in_sample)
        periods["in_sample"] = (candles[:cut], 0)
        periods["out_of_sample"] = (candles, cut)

    report = {
        "data": args.data,
        "first_candle": candles[0].open_time.isoformat(),
        "last_candle": candles[-1].open_time.isoformat(),
        "strategy": args.strategy,
        "data_gaps": len(gaps),
        "first_gaps": [
            [before.isoformat(), after.isoformat()] for before, after in gaps[:5]
        ],
        "periods": {},
    }

    for name, (period, trade_from) in periods.items():
        # Fresh strategy per period: some strategies keep state.
        result = run_backtest(period, _make_strategy(args), config, trade_from)
        benchmark = run_backtest(
            period, buy_and_hold(), benchmark_config, trade_from
        )
        report["periods"][name] = {
            "start": period[trade_from].open_time.isoformat(),
            "end": period[-1].open_time.isoformat(),
            "strategy": _summary(result),
            "buy_and_hold": _summary(benchmark),
        }

    print(json.dumps(report, indent=2))
    return 0


def command_walk_forward(args) -> int:
    """Independent train/test folds for a fixed SMA window (long/flat)."""
    candles = load_csv(args.data)
    gaps = find_gaps(candles)
    if gaps and args.require_continuous:
        raise MarketDataError(f"{len(gaps)} gaps in data")

    report = evaluate_sma_report(
        to_bars(candles),
        window=args.window,
        train_size=args.train,
        test_size=args.test,
        periods_per_year=round(bars_per_year(candles)),
        # Same per-fill costs as `run`: percent -> basis points.
        config=QuantConfig(fee_bps=args.fee * 100,
                           slippage_bps=args.slippage * 100),
    )
    for fold in report["folds"]:
        for key in ("train_start", "train_end", "test_start"):
            fold[key + "_time"] = candles[fold[key]].open_time.isoformat()
        fold["test_end_time"] = candles[fold["test_end"] - 1].open_time.isoformat()
    report["data"] = args.data
    report["data_gaps"] = len(gaps)
    print(json.dumps(report, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="backtest_cli")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="Download Binance candles to CSV")
    fetch.add_argument("--symbol", default="BTCUSDT")
    fetch.add_argument("--interval", default="4h")
    fetch.add_argument("--start", required=True, help="e.g. 2019-01-01")
    fetch.add_argument("--end", help="default: now")
    fetch.add_argument("--out", required=True)
    fetch.set_defaults(handler=command_fetch)

    run = sub.add_parser("run", help="Backtest a strategy on a CSV file")
    run.add_argument("--data", required=True)
    run.add_argument("--strategy", choices=sorted(STRATEGIES),
                     default="sma_crossover")
    run.add_argument("--fast", type=int, default=20)
    run.add_argument("--slow", type=int, default=50)
    run.add_argument("--entry", type=int, default=55)
    run.add_argument("--exit", type=int, default=20)
    run.add_argument("--equity", type=float, default=10_000.0)
    run.add_argument("--fee", type=float, default=0.10,
                     help="percent per fill")
    run.add_argument("--slippage", type=float, default=0.05,
                     help="percent per fill")
    run.add_argument("--allocation", type=float, default=100.0)
    run.add_argument("--stop-loss", type=float)
    run.add_argument("--allow-short", action="store_true")
    run.add_argument("--risk-per-trade", type=float,
                     help="percent of equity; enables risk-engine sizing")
    run.add_argument("--max-daily-loss", type=float, default=3.0)
    run.add_argument("--max-drawdown", type=float, default=25.0)
    run.add_argument("--no-risk-gate", action="store_true",
                     help="research only: run without risk-engine sizing")
    run.add_argument("--require-continuous", action="store_true",
                     help="fail if candles are missing")
    run.add_argument("--in-sample", type=float, default=70.0,
                     help="percent of data for in-sample; the rest is out-of-sample")
    run.set_defaults(handler=command_run)

    walk = sub.add_parser(
        "walk-forward",
        help="SMA long/flat walk-forward folds versus buy-and-hold",
    )
    walk.add_argument("--data", required=True)
    walk.add_argument("--window", type=int, default=50)
    walk.add_argument("--train", type=int, default=1000,
                      help="candles per training (warm-up) window")
    walk.add_argument("--test", type=int, default=500,
                      help="candles per out-of-sample test window")
    walk.add_argument("--fee", type=float, default=0.10)
    walk.add_argument("--slippage", type=float, default=0.05)
    walk.add_argument("--require-continuous", action="store_true")
    walk.set_defaults(handler=command_walk_forward)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (MarketDataError, ValueError) as exc:
        print("Error:", exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
