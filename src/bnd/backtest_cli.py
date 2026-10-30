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
import os
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
    fetch_yahoo_daily,
    repair_spikes,
    find_gaps,
    load_csv,
    save_csv,
    to_bars,
)
from .portfolio import (
    PortfolioConfig,
    portfolio_permutation_test,
    record_signals,
    run_portfolio,
)
from .quant_backtest import BacktestConfig as QuantConfig
from .quant_report import evaluate_sma_report
from .risk_engine import RiskLimits
from .robustness import (
    cost_stress,
    holm_adjust,
    parameter_grid,
    parameter_sets,
    parse_range,
    parse_value,
    permutation_test,
    record_targets,
    select_in_sample,
    summarize_grid,
)
from .strategies import STRATEGIES, SWEEP_RANGES, buy_and_hold
from .universe import select as select_markets
from .walk_forward import walk_forward

# Older dedicated options, kept working: (strategy, option, parameter).
LEGACY_PARAMS = (
    ("sma_crossover", "fast", "fast"),
    ("sma_crossover", "slow", "slow"),
    ("donchian_breakout", "entry", "entry"),
    ("donchian_breakout", "exit", "exit"),
    ("volatility_target", "target_vol", "target_vol"),
    ("volatility_target", "vol_lookback", "lookback"),
    ("volatility_target", "trend", "trend"),
    ("volatility_target", "long_short", "long_short"),
)
LEGACY_RANGES = {
    "sma_crossover": {"fast": "fast_range", "slow": "slow_range"},
    "donchian_breakout": {"entry": "entry_range", "exit": "exit_range"},
    "volatility_target": {"target_vol": "target_vol_range",
                          "lookback": "vol_lookback_range"},
}

SUMMARY_KEYS = (
    "net_profit",
    "total_return_pct",
    "cagr_pct",
    "max_drawdown_pct",
    "volatility_pct",
    "sharpe",
    "sortino",
    "calmar",
    "expectancy",
    "turnover",
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


def _pairs(items, what) -> dict:
    """Parse repeated name=value options."""
    result = {}
    for item in items or ():
        name, sep, value = item.partition("=")
        if not sep or not name.strip():
            raise ValueError(f"{what} must look like name=value, got {item!r}")
        result[name.strip()] = value.strip()
    return result


def _strategy_params(args) -> dict:
    # Commands without the legacy options (e.g. portfolio) skip them.
    params = {
        parameter: getattr(args, option)
        for strategy, option, parameter in LEGACY_PARAMS
        if strategy == args.strategy and hasattr(args, option)
    }
    params.update({
        name: parse_value(value)
        for name, value in _pairs(args.param, "--param").items()
    })
    return params


def _factory(name, fixed: dict):
    """Strategy factory with fixed parameters; bad names become ValueError."""
    base = STRATEGIES[name]

    def factory(**params):
        try:
            return base(**{**fixed, **params})
        except TypeError as exc:
            raise ValueError(f"Invalid parameters for {name}: {exc}") from exc

    return factory


def _make_strategy(args):
    return _factory(args.strategy, _strategy_params(args))()


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
    if not 1 <= args.leverage <= 10:
        raise ValueError("Leverage must be between 1 and 10")
    if args.max_leverage is None:
        args.max_leverage = args.leverage
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
            max_gross_exposure_pct=100.0 * args.max_leverage,
            max_leverage=args.max_leverage,
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
        allocation_pct=args.allocation * args.leverage,
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
        "leverage": config.allocation_pct / 100,
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
    if args.strategy not in SWEEP_RANGES:
        raise ValueError("Robustness needs a strategy with parameters")

    candles, dataset = _load_checked(args)
    config, benchmark_config = _build_configs(args)
    cut = split_index(len(candles), args.in_sample)

    texts = dict(SWEEP_RANGES[args.strategy])
    for name, option in LEGACY_RANGES.get(args.strategy, {}).items():
        texts[name] = getattr(args, option)
    texts.update(_pairs(args.range, "--range"))
    ranges = {name: parse_range(text) for name, text in texts.items()}

    # Swept parameters vary; every other parameter stays fixed.
    fixed = {k: v for k, v in _strategy_params(args).items() if k not in ranges}
    factory = _factory(args.strategy, fixed)
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


def _sweep(args):
    """Parameter ranges (defaults, legacy options, --range) and fixed params."""
    if args.strategy not in SWEEP_RANGES:
        raise ValueError("This command needs a strategy with parameters")
    texts = dict(SWEEP_RANGES[args.strategy])
    for name, option in LEGACY_RANGES.get(args.strategy, {}).items():
        if hasattr(args, option):
            texts[name] = getattr(args, option)
    texts.update(_pairs(getattr(args, "range", None), "--range"))
    ranges = {name: parse_range(text) for name, text in texts.items()}
    fixed = {k: v for k, v in _strategy_params(args).items() if k not in ranges}
    return ranges, fixed


def command_walk_forward_opt(args) -> int:
    """Re-optimise on each training window; trade the next unseen window."""
    candles, dataset = _load_checked(args)
    config, _ = _build_configs(args)
    ranges, fixed = _sweep(args)
    report = walk_forward(
        candles, _factory(args.strategy, fixed), parameter_sets(**ranges), config,
        train=args.train, test=args.test, embargo=args.embargo, mode=args.mode,
        disable_below=None if args.no_switch_off else args.disable_below,
        disable_after=args.disable_after,
    )
    report.update(dataset=dataset, strategy=args.strategy)
    print(json.dumps(_rounded(report), indent=2))
    return 0


def command_compare(args) -> int:
    """Run every strategy with default parameters and rank them on
    out-of-sample Sharpe, each with its own permutation test."""
    candles, dataset = _load_checked(args)
    config, benchmark_config = _build_configs(args)
    cut = split_index(len(candles), args.in_sample)

    def metrics(result):
        keys = ("total_return_pct", "sharpe", "max_drawdown_pct", "trades",
                "avg_capital_exposure_pct", "total_funding")
        return {key: result.metrics.get(key) for key in keys}

    benchmark = {
        "in_sample": metrics(run_backtest(candles[:cut], buy_and_hold(), benchmark_config)),
        "out_of_sample": metrics(
            run_backtest(candles, buy_and_hold(), benchmark_config, cut)
        ),
    }
    rows = []
    for name in sorted(SWEEP_RANGES):
        factory = _factory(name, {})
        in_sample = run_backtest(candles[:cut], factory(), config)
        result, targets = record_targets(candles, factory(), config, cut)
        permutation = permutation_test(
            candles, targets, config, cut, args.permutations, args.seed
        )
        rows.append({
            "strategy": name,
            "in_sample": metrics(in_sample),
            "out_of_sample": metrics(result),
            "p_value": permutation["p_value"],
        })

    for row, adjusted in zip(rows, holm_adjust([row["p_value"] for row in rows])):
        row["p_value_adjusted"] = adjusted

    def score(row):
        sharpe = row["out_of_sample"]["sharpe"]
        return sharpe if sharpe is not None else float("-inf")

    rows.sort(key=score, reverse=True)
    report = {
        **dataset,
        "costs": _cost_settings(config),
        "risk_gate": (
            "enforced" if config.risk_limits is not None
            else "disabled_research_only"
        ),
        "out_of_sample_start": candles[cut].open_time.isoformat(),
        "buy_and_hold": benchmark,
        "ranking": rows,
        "note": (
            "Default parameters, no tuning. Ranked by out-of-sample Sharpe. "
            "p_value_adjusted (Holm) accounts for testing every strategy at "
            "once; above 0.05 the timing is indistinguishable from luck."
        ),
    }
    print(json.dumps(_rounded(report), indent=2))
    return 0


def _split_list(text):
    return [item.strip() for item in (text or "").split(",") if item.strip()]


def command_fetch_universe(args) -> int:
    """Download daily candles for every selected market; skip failures."""
    markets = select_markets(_split_list(args.markets), _split_list(args.classes), args.universe)
    end = _utc_date(args.end) if args.end else datetime.now(timezone.utc)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    quality, failures = {}, {}
    for market in markets:
        try:
            candles, report = fetch_yahoo_daily(market.symbol, _utc_date(args.start), end)
            if not args.keep_spikes:
                candles, repairs = repair_spikes(candles)
                report["repaired_spikes"] = repairs
            save_csv(candles, out / f"{market.name}.csv")
            quality[market.name] = {"symbol": market.symbol, **report,
                                    "first": candles[0].open_time.isoformat(),
                                    "last": candles[-1].open_time.isoformat()}
            print(f"{market.name}: {len(candles)} candles")
        except MarketDataError as exc:
            failures[market.name] = str(exc)
            print(f"{market.name}: FAILED ({exc})", file=sys.stderr)
    (out / "quality.json").write_text(
        json.dumps({"markets": quality, "failures": failures}, indent=2))
    if not quality:
        raise MarketDataError("No market could be downloaded")
    return 0


def _data_diagnostics(data) -> list[dict]:
    """Largest daily move per market, to expose bad prints and roll jumps."""
    rows = []
    for name, candles in data.items():
        moves = [(100 * (b.close / a.close - 1), b.open_time)
                 for a, b in zip(candles, candles[1:])]
        biggest = max(moves, key=lambda move: abs(move[0]))
        rows.append({
            "market": name,
            "largest_move_pct": biggest[0],
            "largest_move_date": biggest[1].date().isoformat(),
            "days_over_15pct": sum(abs(move) > 15 for move, _ in moves),
        })
    rows.sort(key=lambda row: abs(row["largest_move_pct"]), reverse=True)
    return rows


def _portfolio_config(args, **overrides) -> PortfolioConfig:
    values = dict(
        sizing=args.sizing,
        target_vol_pct=args.portfolio_vol,
        vol_lookback=args.sizing_lookback,
        max_leverage=args.max_leverage,
        max_weight=args.max_weight,
        rebalance_threshold=args.rebalance / 100,
        financing_pct_annual=args.financing,
        cash_rate_pct_annual=args.cash_rate,
        max_drawdown_pct=args.max_drawdown or None,
        allow_short=not args.no_shorts,
    )
    values.update(overrides)
    return PortfolioConfig(**values)


def _portfolio_metrics(result) -> dict:
    keys = ("net_profit", "total_return_pct", "cagr_pct", "sharpe", "sortino", "calmar",
            "volatility_pct", "max_drawdown_pct", "turnover", "fills",
            "avg_gross_leverage", "max_gross_leverage", "total_fees",
            "total_financing", "total_interest", "kill_switch_at", "years")
    return {key: result["metrics"].get(key) for key in keys}


def command_portfolio(args) -> int:
    """Trade every market in one account; compare with an equal-weight basket."""
    markets = select_markets(_split_list(args.markets), _split_list(args.classes), args.universe)
    folder = Path(args.data_dir)
    missing = [m.name for m in markets if not (folder / f"{m.name}.csv").exists()]
    if args.skip_missing:
        markets = tuple(m for m in markets if m.name not in missing)
    elif missing:
        raise ValueError("Missing data for: " + ", ".join(missing)
                         + " (use --skip-missing to ignore)")
    if not markets:
        raise ValueError("No market data found")
    data = {m.name: load_csv(folder / f"{m.name}.csv") for m in markets}
    times = sorted({c.open_time for candles in data.values() for c in candles})
    cut = times[int(len(times) * args.in_sample / 100)]
    config = _portfolio_config(args)
    basket = _portfolio_config(args, sizing="equal", max_leverage=1.0, max_weight=1.0,
                               financing_pct_annual=0.0, max_drawdown_pct=None,
                               allow_short=False)

    # In-sample uses only markets with enough history before the split.
    minimum = args.sizing_lookback + 2
    early = {name: [c for c in candles if c.open_time < cut] for name, candles in data.items()}
    early_markets = [m for m in markets if len(early[m.name]) >= minimum]

    names = sorted(SWEEP_RANGES) if args.strategy == "all" else [args.strategy]
    params = {} if args.strategy == "all" else _strategy_params(args)

    def periods(factory, cfg):
        in_sample = run_portfolio(early, early_markets, factory, cfg)
        out_of_sample, signals = record_signals(data, markets, factory, cfg, trade_from=cut)
        return in_sample, out_of_sample, signals

    workers = max(1, min(4, os.cpu_count() or 1))

    basket_oos = run_portfolio(data, markets, buy_and_hold, basket, trade_from=cut)
    rows = []
    for name in names:
        factory = _factory(name, params)
        in_sample, out_of_sample, signals = periods(factory, config)
        row = {
            "strategy": name,
            "in_sample": _portfolio_metrics(in_sample),
            "out_of_sample": _portfolio_metrics(out_of_sample),
        }
        if args.permutations:
            test = portfolio_permutation_test(data, markets, signals, config, cut,
                                              args.permutations, args.seed, workers)
            row["permutation_test_out_of_sample"] = test
            row["p_value"] = test["p_value"]
        if len(names) == 1:
            row["per_market_out_of_sample"] = out_of_sample["per_market"]
            row["cost_stress_out_of_sample"] = [
                {"cost_multiplier": m, **_portfolio_metrics(run_portfolio(
                    data, markets, factory, _portfolio_config(args, cost_multiplier=m),
                    trade_from=cut))}
                for m in (2.0, 3.0)
            ]
            row["leverage_out_of_sample"] = [
                {"max_leverage": lev, **_portfolio_metrics(run_portfolio(
                    data, markets, factory, _portfolio_config(args, max_leverage=lev),
                    trade_from=cut))}
                for lev in sorted({1.0, 2.0, 3.0, 5.0, args.max_leverage})
            ]
        rows.append(row)

    def score(row):
        sharpe = row["out_of_sample"]["sharpe"]
        return sharpe if sharpe is not None else float("-inf")

    if args.permutations:
        for row, adjusted in zip(rows, holm_adjust([row["p_value"] for row in rows])):
            row["p_value_adjusted"] = adjusted
    rows.sort(key=score, reverse=True)
    report = {
        "mode": "portfolio",
        "universe": args.universe,
        "markets": [{"name": m.name, "asset_class": m.asset_class,
                     "candles": len(data[m.name]),
                     "first": data[m.name][0].open_time.isoformat()} for m in markets],
        "skipped_missing": missing if args.skip_missing else [],
        "in_sample_markets": [m.name for m in early_markets],
        "out_of_sample_start": cut.isoformat(),
        "settings": {
            "sizing": config.sizing, "portfolio_vol_pct": config.target_vol_pct,
            "max_leverage": config.max_leverage, "max_weight": config.max_weight,
            "financing_pct_annual": config.financing_pct_annual,
            "cash_rate_pct_annual": config.cash_rate_pct_annual,
            "max_drawdown_pct": config.max_drawdown_pct,
            "allow_short": config.allow_short, "params": params,
        },
        "equal_weight_basket_out_of_sample": _portfolio_metrics(basket_oos),
        "data_diagnostics": _data_diagnostics(data),
        "ranking": rows,
        "note": (
            "Paper research. With --universe futures, futures series are not "
            "roll-adjusted and indices stand in for futures/CFDs; --universe etf "
            "uses tradable, adjusted ETFs. The permutation test shuffles each "
            "market's signal timing; p_value_adjusted (Holm) accounts for "
            "comparing several strategies. Always-long strategies get p = 1: "
            "their result comes from diversification and leverage, not timing."
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
    common.add_argument("--param", action="append", metavar="NAME=VALUE",
                        help="strategy parameter, repeatable (e.g. --param period=21)")
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
    common.add_argument("--leverage", type=float, default=1.0,
                        help="position size multiple of equity (e.g. 3 = 3x)")
    common.add_argument("--max-leverage", type=float,
                        help="risk-engine leverage cap; default = --leverage")
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
    robust.add_argument("--range", action="append", metavar="NAME=START:STOP:STEP",
                        help="sweep range for a parameter, repeatable")
    robust.add_argument("--permutations", type=int, default=200)
    robust.add_argument("--seed", type=int, default=7)
    robust.add_argument("--full-grid", action="store_true",
                        help="include every grid row in the report")
    robust.set_defaults(handler=command_robustness)

    wfo = sub.add_parser("walk-forward-opt", parents=[common],
                         help="Rolling/expanding re-optimisation with unseen test windows")
    wfo.add_argument("--range", action="append", metavar="NAME=START:STOP:STEP")
    wfo.add_argument("--train", type=int, default=1000)
    wfo.add_argument("--test", type=int, default=250)
    wfo.add_argument("--embargo", type=int, default=5,
                     help="candles skipped between training and testing")
    wfo.add_argument("--mode", choices=["rolling", "expanding"], default="rolling")
    wfo.add_argument("--disable-below", type=float, default=0.0,
                     help="switch off after the last folds' mean Sharpe falls below this")
    wfo.add_argument("--disable-after", type=int, default=2)
    wfo.add_argument("--no-switch-off", action="store_true")
    wfo.set_defaults(handler=command_walk_forward_opt)

    compare = sub.add_parser(
        "compare", parents=[common],
        help="Rank every strategy out-of-sample (default parameters)",
    )
    compare.add_argument("--permutations", type=int, default=100)
    compare.add_argument("--seed", type=int, default=7)
    compare.set_defaults(handler=command_compare)

    universe = sub.add_parser("fetch-universe",
                              help="Download daily candles for forex, commodities, indices, crypto")
    universe.add_argument("--start", default="2010-01-01")
    universe.add_argument("--end")
    universe.add_argument("--markets", help="comma-separated names, default all")
    universe.add_argument("--classes", help="e.g. forex,commodity,index,bond,crypto")
    universe.add_argument("--universe", choices=["futures", "etf"], default="futures",
                          help="etf: tradable roll-free ETFs instead of futures/indices")
    universe.add_argument("--out-dir", required=True)
    universe.add_argument("--keep-spikes", action="store_true",
                          help="do not repair one-day spikes that immediately revert")
    universe.set_defaults(handler=command_fetch_universe)

    port = sub.add_parser("portfolio", help="Trade every market in one leveraged account")
    port.add_argument("--data-dir", required=True)
    port.add_argument("--markets")
    port.add_argument("--classes")
    port.add_argument("--universe", choices=["futures", "etf"], default="futures")
    port.add_argument("--skip-missing", action="store_true")
    port.add_argument("--strategy", choices=["all"] + sorted(SWEEP_RANGES),
                      default="all")
    port.add_argument("--param", action="append", metavar="NAME=VALUE")
    port.add_argument("--sizing", choices=["volatility", "equal"], default="volatility")
    port.add_argument("--portfolio-vol", type=float, default=15.0,
                      help="annual portfolio volatility target, percent")
    port.add_argument("--sizing-lookback", type=int, default=60)
    port.add_argument("--max-leverage", type=float, default=3.0)
    port.add_argument("--max-weight", type=float, default=1.0,
                      help="largest |weight| for one market")
    port.add_argument("--rebalance", type=float, default=5.0,
                      help="resize when a weight moves this many points")
    port.add_argument("--financing", type=float, default=0.0,
                      help="extra annual %% on exposure above equity (margin loans/CFDs); "
                           "per-market carry such as crypto funding always applies")
    port.add_argument("--cash-rate", type=float, default=0.0)
    port.add_argument("--max-drawdown", type=float, default=30.0,
                      help="kill switch in percent; 0 disables")
    port.add_argument("--no-shorts", action="store_true")
    port.add_argument("--in-sample", type=float, default=70.0)
    port.add_argument("--permutations", type=int, default=40,
                      help="timing shuffles per strategy (0 disables)")
    port.add_argument("--seed", type=int, default=7)
    port.set_defaults(handler=command_portfolio)

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
