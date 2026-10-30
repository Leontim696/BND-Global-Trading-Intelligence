"""Command line for downloading data and running backtests.

    python -m src.bnd.backtest_cli fetch --symbol BTCUSDT --interval 4h \\
        --start 2019-01-01 --out data/BTCUSDT-4h.csv
    python -m src.bnd.backtest_cli run --data data/BTCUSDT-4h.csv \\
        --strategy sma_crossover --fast 20 --slow 50 --stop-loss 5

Every run is compared with buy-and-hold under the same costs and
reported separately for the in-sample and out-of-sample periods.
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

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
from .robustness import (
    cost_stress,
    parameter_grid,
    parameter_sets,
    parse_range,
    permutation_test,
    record_targets,
    select_in_sample,
    summarize_grid,
)
from .strategies import STRATEGIES, buy_and_hold

# Strategy parameters swept by `robustness`, as (option, factory argument).
SWEEP_PARAMS = {
    "sma_crossover": (("fast", "fast"), ("slow", "slow")),
    "donchian_breakout": (("entry", "entry"), ("exit", "exit")),
    "volatility_target": (("target_vol", "target_vol"), ("vol_lookback", "lookback")),
}

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
    "total_funding",
    "total_interest",
    "time_in_market_pct",
    "avg_capital_exposure_pct",
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
    if args.strategy == "volatility_target":
        return factory(target_vol=args.target_vol, lookback=args.vol_lookback,
                       trend=args.trend, long_short=args.long_short)
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


def _sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_checked(args):
    """Load candles, enforce --require-continuous, describe the dataset."""
    candles = load_csv(args.data)
    gaps = find_gaps(candles)
    if gaps and args.require_continuous:
        raise MarketDataError(
            f"{len(gaps)} gaps in data; first after "
            + gaps[0][0].isoformat()
        )
    dataset = {
        "data": args.data,
        "sha256": _sha256(args.data),
        "candles": len(candles),
        "first_candle": candles[0].open_time.isoformat(),
        "last_candle": candles[-1].open_time.isoformat(),
        "data_gaps": len(gaps),
        "first_gaps": [
            [before.isoformat(), after.isoformat()] for before, after in gaps[:5]
        ],
    }
    return candles, dataset


def _build_configs(args):
    """Strategy and benchmark configs shared by `run` and `robustness`."""
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

    allow_short = args.allow_short or args.long_short
    # Default funding: perpetual-style carry when shorting, none for spot.
    funding = args.funding if args.funding is not None else (
        10.0 if allow_short else 0.0
    )
    config = BacktestConfig(
        initial_equity=args.equity,
        costs=CostModel(
            fee_pct=args.fee,
            slippage_pct=args.slippage,
            funding_pct_annual=funding,
            cash_rate_pct_annual=args.cash_rate,
        ),
        allocation_pct=args.allocation,
        stop_loss_pct=args.stop_loss,
        allow_short=allow_short,
        risk_limits=risk_limits,
        rebalance_threshold=args.rebalance / 100,
    )
    # Buy-and-hold is a spot holding: same fills, no funding.
    benchmark_config = BacktestConfig(
        initial_equity=args.equity,
        costs=CostModel(
            fee_pct=args.fee,
            slippage_pct=args.slippage,
            cash_rate_pct_annual=args.cash_rate,
        ),
    )
    return config, benchmark_config


def _cost_settings(config) -> dict:
    return {
        "fee_pct": config.costs.fee_pct,
        "slippage_pct": config.costs.slippage_pct,
        "funding_pct_annual": config.costs.funding_pct_annual,
        "cash_rate_pct_annual": config.costs.cash_rate_pct_annual,
        "allow_short": config.allow_short,
    }


def command_run(args) -> int:
    candles, dataset = _load_checked(args)
    config, benchmark_config = _build_configs(args)

    # (candles, first traded index). Out-of-sample trading starts at the
    # split, but strategies warm up on the preceding in-sample candles.
    periods = {"full": (candles, 0)}
    if args.in_sample is not None:
        cut = split_index(len(candles), args.in_sample)
        periods["in_sample"] = (candles[:cut], 0)
        periods["out_of_sample"] = (candles, cut)

    report = {
        **dataset,
        "strategy": args.strategy,
        "costs": _cost_settings(config),
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
    candles, dataset = _load_checked(args)

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
    report["dataset"] = dataset
    print(json.dumps(report, indent=2))
    return 0


def _rounded(value):
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_rounded(item) for item in value]
    return value


def command_robustness(args) -> int:
    """Parameter grid, in-sample selection, permutation and cost stress."""
    if args.strategy not in SWEEP_PARAMS:
        raise ValueError("Robustness needs a strategy with parameters")

    candles, dataset = _load_checked(args)
    config, benchmark_config = _build_configs(args)
    cut = split_index(len(candles), args.in_sample)
    factory = STRATEGIES[args.strategy]
    if args.strategy == "volatility_target":
        # Keep the fixed --trend filter while sweeping the other parameters.
        base = factory
        def factory(**params):
            return base(trend=args.trend, long_short=args.long_short, **params)
    ranges = {
        name: parse_range(getattr(args, option + "_range"))
        for option, name in SWEEP_PARAMS[args.strategy]
    }
    params = parameter_sets(**ranges)

    periods = {
        "in_sample": (candles[:cut], 0),
        "out_of_sample": (candles, cut),
    }
    grids, summaries = {}, {}
    for name, (period, trade_from) in periods.items():
        benchmark = run_backtest(
            period, buy_and_hold(), benchmark_config, trade_from
        ).metrics["total_return_pct"]
        grids[name] = parameter_grid(period, factory, params, config, trade_from)
        summaries[name] = summarize_grid(grids[name], benchmark)

    selection = select_in_sample(grids["in_sample"], grids["out_of_sample"])
    chosen = selection["params"]

    # Judge the in-sample choice on unseen data only.
    _, targets = record_targets(candles, factory(**chosen), config, cut)
    permutation = permutation_test(
        candles, targets, config, cut, args.permutations, args.seed
    )
    stress = cost_stress(
        candles, lambda: factory(**chosen), config, trade_from=cut
    )

    report = {
        **dataset,
        "strategy": args.strategy,
        "risk_gate": (
            "enforced" if config.risk_limits is not None
            else "disabled_research_only"
        ),
        "costs": _cost_settings(config),
        "out_of_sample_start": candles[cut].open_time.isoformat(),
        "grid_summary": summaries,
        "in_sample_selection": selection,
        "permutation_test_out_of_sample": permutation,
        "cost_stress_out_of_sample": stress,
        "grid": grids if args.full_grid else None,
        "note": (
            "Parameters are chosen on in-sample data only. A p_value above "
            "0.05 means the real timing is not distinguishable from shuffled "
            "timing of the same positions. No profitability is implied."
        ),
    }
    print(json.dumps(_rounded(report), indent=2))
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

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data", required=True)
    common.add_argument("--strategy", choices=sorted(STRATEGIES),
                        default="sma_crossover")
    common.add_argument("--fast", type=int, default=20)
    common.add_argument("--slow", type=int, default=50)
    common.add_argument("--entry", type=int, default=55)
    common.add_argument("--exit", type=int, default=20)
    common.add_argument("--target-vol", type=float, default=40.0,
                        help="volatility_target: annualised target in percent")
    common.add_argument("--vol-lookback", type=int, default=180,
                        help="volatility_target: candles for realised volatility")
    common.add_argument("--trend", type=int, default=0,
                        help="volatility_target: flat below this SMA (0 = off)")
    common.add_argument("--long-short", action="store_true",
                        help="volatility_target: short below the trend (implies --allow-short)")
    common.add_argument("--funding", type=float,
                        help="annual %% charged on open positions; default 10 with shorts, else 0")
    common.add_argument("--cash-rate", type=float, default=0.0,
                        help="annual %% interest on uninvested equity")
    common.add_argument("--rebalance", type=float, default=10.0,
                        help="resize only when target exposure moves this many points")
    common.add_argument("--equity", type=float, default=10_000.0)
    common.add_argument("--fee", type=float, default=0.10,
                        help="percent per fill")
    common.add_argument("--slippage", type=float, default=0.05,
                        help="percent per fill")
    common.add_argument("--allocation", type=float, default=100.0)
    common.add_argument("--stop-loss", type=float)
    common.add_argument("--allow-short", action="store_true")
    common.add_argument("--risk-per-trade", type=float,
                        help="percent of equity; enables risk-engine sizing")
    common.add_argument("--max-daily-loss", type=float, default=3.0)
    common.add_argument("--max-drawdown", type=float, default=25.0)
    common.add_argument("--no-risk-gate", action="store_true",
                        help="research only: run without risk-engine sizing")
    common.add_argument("--require-continuous", action="store_true",
                        help="fail if candles are missing")
    common.add_argument("--in-sample", type=float, default=70.0,
                        help="percent of data for in-sample; the rest is out-of-sample")

    run = sub.add_parser("run", parents=[common],
                         help="Backtest a strategy on a CSV file")
    run.set_defaults(handler=command_run)

    robust = sub.add_parser(
        "robustness", parents=[common],
        help="Parameter grid, permutation test and cost stress",
    )
    robust.add_argument("--fast-range", default="10:50:10")
    robust.add_argument("--slow-range", default="50:200:25")
    robust.add_argument("--entry-range", default="20:100:20")
    robust.add_argument("--exit-range", default="10:50:10")
    robust.add_argument("--target-vol-range", default="20:80:10")
    robust.add_argument("--vol-lookback-range", default="60:360:60")
    robust.add_argument("--permutations", type=int, default=200)
    robust.add_argument("--seed", type=int, default=7)
    robust.add_argument("--full-grid", action="store_true",
                        help="include every grid row in the report")
    robust.set_defaults(handler=command_robustness)

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
