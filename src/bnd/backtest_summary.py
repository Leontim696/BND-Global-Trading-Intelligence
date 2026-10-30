"""Markdown summary of backtest_cli reports, for the GitHub job summary.

    python -m src.bnd.backtest_summary --run report.json \\
        --walk-forward walk-forward.json --robustness robustness.json

Missing or unreadable reports are listed, not fatal: the summary should
explain a partial run rather than hide it.
"""

import argparse
import json
import sys
from pathlib import Path

# Evidence threshold for the permutation test (one-sided).
P_VALUE_THRESHOLD = 0.05


def _fmt(value, suffix="", digits=2) -> str:
    if value is None:
        return "–"
    if isinstance(value, float):
        return f"{value:,.{digits}f}{suffix}"
    return f"{value}{suffix}"


def _load(path):
    if path is None:
        return None, None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except (OSError, ValueError) as exc:
        return None, f"`{path}`: {type(exc).__name__}"


def _dataset_lines(report: dict) -> list[str]:
    return [
        "## Dataset",
        f"- File: `{report.get('data')}` ({report.get('candles')} candles, "
        f"{report.get('data_gaps')} gaps)",
        f"- Range: {report.get('first_candle')} → {report.get('last_candle')}",
        f"- SHA-256: `{report.get('sha256')}`",
        "",
    ]


def _run_lines(report: dict) -> list[str]:
    rows = [
        ("Return", "total_return_pct", "%"),
        ("CAGR", "cagr_pct", "%"),
        ("Max drawdown", "max_drawdown_pct", "%"),
        ("Sharpe", "sharpe", ""),
        ("Trades", "trades", ""),
        ("Time in market", "time_in_market_pct", "%"),
        ("Avg capital exposure", "avg_capital_exposure_pct", "%"),
        ("Funding paid", "total_funding", ""),
        ("Interest earned", "total_interest", ""),
        # Every candle a vetoed entry is retried counts once.
        ("Entries vetoed by risk engine", "rejected_entries", ""),
    ]
    lines = [f"## Backtest: `{report.get('strategy')}`"]
    costs = report.get("costs")
    if costs:
        lines.append(
            f"Costs per fill: fee {costs['fee_pct']}%, slippage {costs['slippage_pct']}%; "
            f"funding {costs['funding_pct_annual']}%/yr on open positions; "
            f"cash interest {costs['cash_rate_pct_annual']}%/yr; "
            f"shorts {'allowed' if costs['allow_short'] else 'off'}."
        )
    for name, period in report.get("periods", {}).items():
        strategy, benchmark = period["strategy"], period["buy_and_hold"]
        lines += [
            "",
            f"**{name}** ({period['start']} → {period['end']}, "
            f"risk gate: {strategy.get('risk_gate')})",
            "",
            "| Metric | Strategy | Buy & hold |",
            "| --- | ---: | ---: |",
        ]
        lines += [
            f"| {label} | {_fmt(strategy.get(key), unit)} | "
            f"{_fmt(benchmark.get(key), unit)} |"
            for label, key, unit in rows
        ]
    return lines + [""]


def _walk_forward_lines(report: dict) -> list[str]:
    summary = report.get("summary", {})
    return [
        "## Walk-forward (SMA long/flat, independent folds)",
        f"- Folds: {summary.get('fold_count')}, beating buy & hold: "
        f"{summary.get('outperforming_fold_count')}",
        f"- Excess return per fold: mean "
        f"{_fmt(summary.get('mean_excess_net_return_pct'), ' pp')}, median "
        f"{_fmt(summary.get('median_excess_net_return_pct'), ' pp')}",
        "",
    ]


def _robustness_lines(report: dict) -> list[str]:
    lines = ["## Robustness", "", "| Period | Combos | Beat B&H | Profitable | Median return | B&H |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, grid in report.get("grid_summary", {}).items():
        lines.append(
            f"| {name} | {grid['combinations']} | "
            f"{_fmt(grid['beat_buy_and_hold_pct'], '%', 0)} | {grid['profitable']} | "
            f"{_fmt(grid['median_return_pct'], '%')} | "
            f"{_fmt(grid['buy_and_hold_return_pct'], '%')} |"
        )

    selection = report.get("in_sample_selection", {})
    ins, oos = selection.get("in_sample", {}), selection.get("out_of_sample", {})
    params = ", ".join(
        f"{key}={value}" for key, value in (selection.get("params") or {}).items()
    ) or "–"
    lines += [
        "",
        f"**In-sample choice** {params}: in-sample return "
        f"{_fmt(ins.get('total_return_pct'), '%')} (Sharpe {_fmt(ins.get('sharpe'))}); "
        f"out-of-sample return {_fmt(oos.get('total_return_pct'), '%')} "
        f"(Sharpe {_fmt(oos.get('sharpe'))}), rank "
        f"{selection.get('out_of_sample_rank')} of "
        f"{selection.get('out_of_sample_combinations')}.",
    ]

    perm = report.get("permutation_test_out_of_sample", {})
    lines += [
        "",
        f"**Permutation test** (out-of-sample, {perm.get('permutations')} shuffles): "
        f"actual {_fmt(perm.get('actual_return_pct'), '%')}, shuffled median "
        f"{_fmt(perm.get('shuffled_median_return_pct'), '%')}, 5–95% range "
        f"{_fmt(perm.get('shuffled_p5_return_pct'), '%')} … "
        f"{_fmt(perm.get('shuffled_p95_return_pct'), '%')}, "
        f"p-value **{_fmt(perm.get('p_value'), digits=3)}**.",
        "",
        "| Cost multiplier | Return | Sharpe | Trades |",
        "| ---: | ---: | ---: | ---: |",
    ]
    lines += [
        f"| ×{_fmt(row['cost_multiplier'], digits=0)} | "
        f"{_fmt(row['total_return_pct'], '%')} | {_fmt(row['sharpe'])} | {row['trades']} |"
        for row in report.get("cost_stress_out_of_sample", [])
    ]
    return lines + [""]


def verdict(robustness: dict | None) -> str:
    """One conservative sentence; every condition must hold for 'evidence'."""

    if not robustness:
        return "No robustness report: no conclusion about an edge is possible."

    perm = robustness.get("permutation_test_out_of_sample", {})
    oos = robustness.get("in_sample_selection", {}).get("out_of_sample", {})
    stress = {
        row["cost_multiplier"]: row["total_return_pct"]
        for row in robustness.get("cost_stress_out_of_sample", [])
    }
    checks = {
        f"permutation p-value < {P_VALUE_THRESHOLD}":
            (perm.get("p_value") or 1) < P_VALUE_THRESHOLD,
        "positive out-of-sample return": (oos.get("total_return_pct") or 0) > 0,
        "still positive at 2× costs": (stress.get(2.0) or 0) > 0,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        return ("**No evidence of an edge.** Failed: " + "; ".join(failed)
                + ". Treat any profit above as luck or overfitting.")
    return ("**Preliminary evidence of an edge** on this dataset only. "
            "Confirm on other periods and markets and in paper trading "
            "before trusting it; this is not a profitability guarantee.")


def risk_adjusted_line(run: dict | None) -> str | None:
    """Out-of-sample Sharpe, drawdown and exposure versus buy-and-hold."""

    period = (run or {}).get("periods", {}).get("out_of_sample")
    if not period:
        return None
    strategy, benchmark = period["strategy"], period["buy_and_hold"]
    return (
        f"Out-of-sample, risk-adjusted: Sharpe {_fmt(strategy.get('sharpe'))} vs "
        f"{_fmt(benchmark.get('sharpe'))} for buy & hold; max drawdown "
        f"{_fmt(strategy.get('max_drawdown_pct'), '%')} vs "
        f"{_fmt(benchmark.get('max_drawdown_pct'), '%')}; return "
        f"{_fmt(strategy.get('total_return_pct'), '%')} vs "
        f"{_fmt(benchmark.get('total_return_pct'), '%')} with "
        f"{_fmt(strategy.get('avg_capital_exposure_pct'), '%')} average capital invested."
    )


def compare_verdict(compare: dict) -> str:
    winners = [
        row["strategy"] for row in compare.get("ranking", [])
        if row.get("p_value_adjusted", 1) < P_VALUE_THRESHOLD
        and (row["out_of_sample"].get("total_return_pct") or 0) > 0
    ]
    if not winners:
        return ("**No strategy shows evidence of an edge** after adjusting for "
                "testing all of them at once. Treat any profit below as luck.")
    return ("**Candidates worth a closer look:** " + ", ".join(winners)
            + ". Run `robustness` on each before trusting them.")


def _compare_lines(report: dict) -> list[str]:
    benchmark = report.get("buy_and_hold", {}).get("out_of_sample", {})
    lines = [
        "## Strategy comparison (out-of-sample, default parameters)",
        "",
        "| # | Strategy | Return | Sharpe | Max drawdown | Trades | Capital invested | p-value (adjusted) |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for rank, row in enumerate(report.get("ranking", []), 1):
        oos = row["out_of_sample"]
        lines.append(
            f"| {rank} | {row['strategy']} | {_fmt(oos.get('total_return_pct'), '%')} | "
            f"{_fmt(oos.get('sharpe'))} | {_fmt(oos.get('max_drawdown_pct'), '%')} | "
            f"{oos.get('trades')} | {_fmt(oos.get('avg_capital_exposure_pct'), '%')} | "
            f"{_fmt(row.get('p_value'), digits=3)} ({_fmt(row.get('p_value_adjusted'), digits=3)}) |"
        )
    lines.append(
        f"| – | buy & hold | {_fmt(benchmark.get('total_return_pct'), '%')} | "
        f"{_fmt(benchmark.get('sharpe'))} | {_fmt(benchmark.get('max_drawdown_pct'), '%')} | "
        f"{benchmark.get('trades')} | {_fmt(benchmark.get('avg_capital_exposure_pct'), '%')} | – |"
    )
    return lines + [""]


def _portfolio_lines(report: dict) -> list[str]:
    settings = report.get("settings", {})
    classes = {}
    for market in report.get("markets", []):
        classes[market["asset_class"]] = classes.get(market["asset_class"], 0) + 1
    basket = report.get("equal_weight_basket_out_of_sample", {})
    lines = [
        "## Multi-market portfolio",
        f"- Markets: {len(report.get('markets', []))} ("
        + ", ".join(f"{count} {name}" for name, count in sorted(classes.items())) + ")"
        + (f"; skipped (no data): {', '.join(report['skipped_missing'])}"
           if report.get("skipped_missing") else ""),
        f"- Out-of-sample from {report.get('out_of_sample_start')}",
        f"- Sizing {settings.get('sizing')}, portfolio volatility target "
        f"{settings.get('portfolio_vol_pct')}%, max leverage {settings.get('max_leverage')}x, "
        f"financing {settings.get('financing_pct_annual')}%/yr, kill switch at "
        f"{settings.get('max_drawdown_pct')}% drawdown, shorts "
        f"{'on' if settings.get('allow_short') else 'off'}",
        "",
        "| # | Strategy | Return | CAGR | Sharpe | Max drawdown | Avg leverage | Fills | Financing | Kill switch |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for rank, row in enumerate(report.get("ranking", []), 1):
        oos = row["out_of_sample"]
        lines.append(
            f"| {rank} | {row['strategy']} | {_fmt(oos.get('total_return_pct'), '%')} | "
            f"{_fmt(oos.get('cagr_pct'), '%')} | {_fmt(oos.get('sharpe'))} | "
            f"{_fmt(oos.get('max_drawdown_pct'), '%')} | {_fmt(oos.get('avg_gross_leverage'), 'x')} | "
            f"{oos.get('fills')} | {_fmt(oos.get('total_financing'))} | "
            f"{(oos.get('kill_switch_at') or '–')[:10]} |"
        )
    lines.append(
        f"| – | equal-weight basket (long, 1x) | {_fmt(basket.get('total_return_pct'), '%')} | "
        f"{_fmt(basket.get('cagr_pct'), '%')} | {_fmt(basket.get('sharpe'))} | "
        f"{_fmt(basket.get('max_drawdown_pct'), '%')} | {_fmt(basket.get('avg_gross_leverage'), 'x')} | "
        f"{basket.get('fills')} | – | – |"
    )
    diagnostics = report.get("data_diagnostics", [])
    if diagnostics:
        lines += ["", "**Largest daily moves (check for bad data):** " + ", ".join(
            f"{d['market']} {_fmt(d['largest_move_pct'], '%', 1)} on {d['largest_move_date']}"
            + (f" ({d['days_over_15pct']} days > 15%)" if d["days_over_15pct"] else "")
            for d in diagnostics[:6])]
    ranking = report.get("ranking", [])
    if len(ranking) == 1:
        row = ranking[0]
        markets = row.get("per_market_out_of_sample", [])
        lines += ["", "**Profit by market (out-of-sample):** "
                  + ", ".join(f"{m['market']} {_fmt(m['pnl'], digits=0)}" for m in markets)]
        lines += ["", "| Max leverage | Return | Sharpe | Max drawdown | Kill switch |",
                  "| ---: | ---: | ---: | ---: | --- |"]
        lines += [
            f"| {_fmt(r['max_leverage'], 'x', 0)} | {_fmt(r.get('total_return_pct'), '%')} | "
            f"{_fmt(r.get('sharpe'))} | {_fmt(r.get('max_drawdown_pct'), '%')} | "
            f"{(r.get('kill_switch_at') or '–')[:10]} |"
            for r in row.get("leverage_out_of_sample", [])
        ]
        lines += ["", "Cost stress: " + "; ".join(
            f"×{_fmt(r['cost_multiplier'], digits=0)} → {_fmt(r.get('total_return_pct'), '%')} "
            f"(Sharpe {_fmt(r.get('sharpe'))})"
            for r in row.get("cost_stress_out_of_sample", []))]
    return lines + [""]


def portfolio_verdict(report: dict) -> str:
    ranking = report.get("ranking", [])
    basket = report.get("equal_weight_basket_out_of_sample", {}).get("sharpe")
    if not ranking:
        return "No strategy results."
    best = ranking[0]
    sharpe = best["out_of_sample"].get("sharpe")
    if sharpe is None or sharpe <= 0 or (basket is not None and sharpe <= basket):
        return ("**No evidence of an edge:** no strategy beat the simple equal-weight "
                "basket on out-of-sample Sharpe.")
    return (f"**Best out-of-sample: {best['strategy']}** (Sharpe {_fmt(sharpe)} vs "
            f"{_fmt(basket)} for the basket). Not yet proven: there is no "
            "permutation test for portfolios and several strategies were compared.")


def build_summary(run=None, walk_forward=None, robustness=None, compare=None,
                  portfolio=None) -> str:
    reports, problems = {}, []
    for name, path in (("run", run), ("walk_forward", walk_forward),
                       ("robustness", robustness), ("compare", compare),
                       ("portfolio", portfolio)):
        data, error = _load(path)
        reports[name] = data
        if error:
            problems.append(error)

    lines = ["# BND backtest summary", ""]
    dataset_source = reports["run"] or reports["robustness"] or reports["compare"]
    if dataset_source:
        lines += _dataset_lines(dataset_source)
    if reports["portfolio"]:
        lines += ["## Verdict", portfolio_verdict(reports["portfolio"]), ""]
        lines += _portfolio_lines(reports["portfolio"])
    elif reports["compare"]:
        lines += ["## Verdict", compare_verdict(reports["compare"]), ""]
        lines += _compare_lines(reports["compare"])
    else:
        lines += ["## Verdict", verdict(reports["robustness"]), ""]
    risk_line = risk_adjusted_line(reports["run"])
    if risk_line:
        lines += [risk_line, ""]
    if reports["run"]:
        lines += _run_lines(reports["run"])
    if reports["walk_forward"]:
        lines += _walk_forward_lines(reports["walk_forward"])
    if reports["robustness"]:
        lines += _robustness_lines(reports["robustness"])
    if problems:
        lines += ["## Missing reports"] + [f"- {p}" for p in problems] + [""]
    lines.append("_Paper research only. Past results do not predict future returns._")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="backtest_summary")
    parser.add_argument("--run")
    parser.add_argument("--walk-forward")
    parser.add_argument("--robustness")
    parser.add_argument("--compare")
    parser.add_argument("--portfolio")
    args = parser.parse_args(argv)
    sys.stdout.write(build_summary(args.run, args.walk_forward, args.robustness,
                                   args.compare, args.portfolio))
    return 0


if __name__ == "__main__":
    sys.exit(main())
