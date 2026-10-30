"""Offline walk-forward performance report; no network or order execution.

Folds are funded independently. Their returns must not be compounded as if
they were a single continuous portfolio. The summary uses arithmetic fold
averages and explicitly states that limitation.
"""
from statistics import mean, median

from .quant_backtest import Bar, BacktestConfig
from .quant_evaluation import evaluate_sma_walk_forward
from .quant_metrics import compare_to_benchmark


def evaluate_sma_report(
    bars: list[Bar],
    window: int,
    train_size: int,
    test_size: int,
    periods_per_year: int,
    config: BacktestConfig = BacktestConfig(),
) -> dict:
    """Evaluate each forward test fold with aligned risk-adjusted metrics."""
    if type(periods_per_year) is not int or periods_per_year <= 0:
        raise ValueError("periods_per_year must be a positive integer")
    folds = evaluate_sma_walk_forward(bars, window, train_size, test_size, config)
    if not folds:
        raise ValueError("Not enough bars for a complete forward-test fold")

    results = []
    for fold in folds:
        strategy = fold["strategy"]
        benchmark = fold["benchmark"]
        # Both equity curves include one training-close warm-up mark.
        # Only the following test_size returns are evaluated.
        if (len(strategy["equity_curve"]) != test_size + 1
                or len(benchmark["equity_curve"]) != test_size + 1):
            raise RuntimeError("Forward fold has unexpected equity curve length")
        metrics = compare_to_benchmark(
            strategy["equity_curve"],
            benchmark["equity_curve"],
            periods_per_year,
        )
        results.append({
            "train_start": fold["train_start"],
            "train_end": fold["train_end"],
            "test_start": fold["test_start"],
            "test_end": fold["test_end"],
            "strategy": metrics["strategy"],
            "benchmark": metrics["benchmark"],
            "excess_net_return_pct": metrics["excess_net_return_pct"],
            "excess_cagr_pct_points": metrics["excess_cagr_pct_points"],
            "strategy_execution_count": strategy["execution_count"],
            "strategy_fees_paid": strategy["fees_paid"],
            "benchmark_execution_count": benchmark["execution_count"],
            "benchmark_fees_paid": benchmark["fees_paid"],
        })

    excess = [fold["excess_net_return_pct"] for fold in results]
    return {
        "strategy": "SMA long/flat (fixed window)",
        "folds": results,
        "summary": {
            "fold_count": len(results),
            "mean_excess_net_return_pct": mean(excess),
            "median_excess_net_return_pct": median(excess),
            "outperforming_fold_count": sum(x > 0 for x in excess),
            "periods_per_year": periods_per_year,
            "note": (
                "Independent test folds with reset capital. Mean/median fold "
                "returns are not compounded portfolio performance; no "
                "parameter optimization or statistical significance implied."
            ),
        },
    }
