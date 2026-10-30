"""Offline strategy performance metrics with explicit sampling assumptions."""
from math import isfinite, sqrt


def performance_metrics(equity_curve: list[float], periods_per_year: int,
                        risk_free_rate_annual: float = 0.0) -> dict:
    """Returns per-period Sharpe, annualized Sharpe, CAGR and drawdown.

    Equity observations must be equally spaced and strictly positive.
    A single observation is not enough for return statistics.
    """
    if type(periods_per_year) is not int or periods_per_year <= 0:
        raise ValueError("periods_per_year must be a positive integer")
    if not isfinite(risk_free_rate_annual) or risk_free_rate_annual <= -1:
        raise ValueError("risk-free annual rate must be finite and > -1")
    if len(equity_curve) < 2:
        raise ValueError("At least two equity observations are required")
    if any(not isinstance(x, (int, float)) or isinstance(x, bool)
           or not isfinite(x) or x <= 0 for x in equity_curve):
        raise ValueError("Equity observations must be positive finite numbers")
    returns = [equity_curve[i] / equity_curve[i - 1] - 1
               for i in range(1, len(equity_curve))]
    n = len(returns)
    mean = sum(returns) / n
    rf_period = (1 + risk_free_rate_annual) ** (1 / periods_per_year) - 1
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1) if n > 1 else 0.0
    std = sqrt(variance)
    sharpe = (mean - rf_period) / std * sqrt(periods_per_year) if std > 0 else None
    peak = equity_curve[0]
    drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        drawdown = max(drawdown, 1 - equity / peak)
    years = n / periods_per_year
    cagr = (equity_curve[-1] / equity_curve[0]) ** (1 / years) - 1
    return {
        "net_return_pct": 100 * (equity_curve[-1] / equity_curve[0] - 1),
        "cagr_pct": 100 * cagr,
        "annualized_sharpe": sharpe,
        "max_drawdown_pct": 100 * drawdown,
        "period_count": n,
        "periods_per_year": periods_per_year,
        "risk_free_rate_annual": risk_free_rate_annual,
        "note": "Equally spaced equity marks assumed; no statistical significance implied",
    }


def compare_to_benchmark(strategy: list[float], benchmark: list[float],
                         periods_per_year: int) -> dict:
    """Compare net results on identical, aligned valuation periods."""
    if len(strategy) != len(benchmark):
        raise ValueError("Strategy and benchmark curves must be aligned")
    a = performance_metrics(strategy, periods_per_year)
    b = performance_metrics(benchmark, periods_per_year)
    return {
        "strategy": a,
        "benchmark": b,
        "excess_net_return_pct": a["net_return_pct"] - b["net_return_pct"],
        "excess_cagr_pct_points": a["cagr_pct"] - b["cagr_pct"],
    }
