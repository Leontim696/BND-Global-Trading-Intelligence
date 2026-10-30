"""Offline tests for Yahoo data, fetch-universe and the portfolio command."""

import contextlib
import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from src.bnd import market_data
from src.bnd.backtest_cli import main as cli
from src.bnd.market_data import Candle, MarketDataError, parse_yahoo_chart, save_csv

START = datetime(2020, 1, 1, tzinfo=timezone.utc)


def yahoo_payload(rows):
    stamps, columns = [], {k: [] for k in ("open", "high", "low", "close", "volume")}
    for stamp, o, h, l, c in rows:
        stamps.append(stamp)
        for key, value in zip(("open", "high", "low", "close", "volume"), (o, h, l, c, 10)):
            columns[key].append(value)
    return {"chart": {"result": [{"timestamp": stamps,
                                  "indicators": {"quote": [columns]}}]}}


def day(n, hour=5):
    return int((START + timedelta(days=n, hours=hour)).timestamp())


def test_yahoo_parsing_cleans_and_reports():
    payload = yahoo_payload([
        (day(0), 10, 11, 9, 10.5),
        (day(1), 10.5, 10.4, 10.2, 10.6),     # high below close: repaired
        (day(2), None, 11, 9, 10),            # missing: dropped
        (day(3), 20, 21, -40, -37.6),         # negative oil price: dropped
        (day(4, 5), 10, 11, 9, 10),
        (day(4, 21), 10, 12, 9, 11),          # same UTC day: keep last
    ])

    candles, quality = parse_yahoo_chart(payload)

    assert [c.close for c in candles] == [10.5, 10.6, 11]
    assert candles[1].high == 10.6 and candles[0].open_time.hour == 0
    assert quality == {"rows": 6, "dropped_missing": 1, "dropped_non_positive": 1,
                       "repaired_high_low": 1, "duplicate_days": 1, "candles": 3,
                       "adjusted_for_dividends_and_splits": False}


def test_yahoo_adjusts_whole_bar_for_dividends():
    payload = yahoo_payload([(day(0), 100, 102, 98, 100), (day(1), 100, 101, 99, 101)])
    # A 2% dividend paid after day 0: earlier prices scale down by 0.98.
    payload["chart"]["result"][0]["indicators"]["adjclose"] = [{"adjclose": [98.0, 101.0]}]

    candles, quality = parse_yahoo_chart(payload)

    first = candles[0]
    assert (first.open, first.high, first.low, first.close) == pytest.approx((98, 99.96, 96.04, 98))
    assert candles[1].close == 101 and quality["adjusted_for_dividends_and_splits"]


def test_etf_universe_is_roll_free_and_selectable():
    from src.bnd.universe import ETF_UNIVERSE, select

    symbols = {m.symbol for m in ETF_UNIVERSE}
    assert {"GLD", "USO", "SPY", "IEF"} <= symbols
    assert not any(m.symbol.endswith("=F") for m in ETF_UNIVERSE)
    assert [m.symbol for m in select(names=["gold"], universe="etf")] == ["GLD"]
    with pytest.raises(ValueError):
        select(universe="moon")


def test_yahoo_bad_payload():
    with pytest.raises(MarketDataError):
        parse_yahoo_chart({"chart": {"result": None}})


class FakeResponse:
    def __init__(self, payload):
        self.raw = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, limit):
        return self.raw[:limit]


def run_cli(args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli(args)
    return code, out.getvalue(), err.getvalue()


def test_fetch_universe_records_failures(tmp_path, monkeypatch):
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        if "GC%3DF" in request.full_url:
            raise market_data.URLError("down")
        assert request.get_header("User-agent")
        return FakeResponse(yahoo_payload([(day(i), 1.1, 1.2, 1.0, 1.1 + i / 1000)
                                           for i in range(30)]))

    monkeypatch.setattr(market_data, "urlopen", fake_urlopen)

    code, out, err = run_cli(["fetch-universe", "--markets", "EURUSD,GOLD",
                              "--start", "2020-01-01", "--end", "2021-01-01",
                              "--out-dir", str(tmp_path)])

    assert code == 0
    assert (tmp_path / "EURUSD.csv").exists() and not (tmp_path / "GOLD.csv").exists()
    quality = json.loads((tmp_path / "quality.json").read_text())
    assert "GOLD" in quality["failures"] and quality["markets"]["EURUSD"]["candles"] == 30
    assert "GOLD: FAILED" in err


def write_markets(folder, names, days=900):
    """Synthetic trending and oscillating markets."""
    for k, name in enumerate(names):
        candles, price = [], 100.0
        for i in range(days):
            drift = (0.001, -0.001, 0.0)[k % 3]
            close = price * (1 + drift) * (1 + 0.01 * (-1) ** (i + k))
            candles.append(Candle(START + timedelta(days=i), price, max(price, close),
                                  min(price, close), close, 1))
            price = close
        save_csv(candles, folder / f"{name}.csv")


def test_portfolio_single_strategy_report(tmp_path):
    write_markets(tmp_path, ["EURUSD", "GOLD", "SP500"])

    code, out, _ = run_cli(["portfolio", "--permutations", "3", "--data-dir", str(tmp_path),
                            "--markets", "EURUSD,GOLD,SP500",
                            "--strategy", "sma_crossover", "--param", "fast=10",
                            "--param", "slow=40", "--max-leverage", "2"])

    assert code == 0
    report = json.loads(out)
    row = report["ranking"][0]
    assert row["strategy"] == "sma_crossover"
    assert report["settings"]["params"] == {"fast": 10, "slow": 40}
    assert {m["market"] for m in row["per_market_out_of_sample"]} == {"EURUSD", "GOLD", "SP500"}
    assert [r["max_leverage"] for r in row["leverage_out_of_sample"]] == [1, 2, 3, 5]
    assert row["out_of_sample"]["max_gross_leverage"] <= 2 + 1e-9
    assert row["permutation_test_out_of_sample"]["permutations"] == 3
    assert row["p_value_adjusted"] >= row["p_value"]
    assert "total_return_pct" in report["equal_weight_basket_out_of_sample"]
    diagnostics = report["data_diagnostics"]
    assert {d["market"] for d in diagnostics} == {"EURUSD", "GOLD", "SP500"}
    assert abs(diagnostics[0]["largest_move_pct"]) >= abs(diagnostics[-1]["largest_move_pct"])


def test_portfolio_all_strategies_and_missing_data(tmp_path):
    write_markets(tmp_path, ["EURUSD", "GOLD"])

    code, _, err = run_cli(["portfolio", "--permutations", "3", "--data-dir", str(tmp_path),
                            "--markets", "EURUSD,GOLD,SP500"])
    assert code == 2 and "Missing data for: SP500" in err

    code, out, _ = run_cli(["portfolio", "--permutations", "3", "--data-dir", str(tmp_path),
                            "--markets", "EURUSD,GOLD,SP500", "--skip-missing"])
    assert code == 0
    report = json.loads(out)
    assert report["skipped_missing"] == ["SP500"]
    assert len(report["ranking"]) >= 10


def test_portfolio_summary(tmp_path):
    from src.bnd.backtest_summary import build_summary, portfolio_verdict

    write_markets(tmp_path, ["EURUSD", "GOLD", "SP500"])
    code, out, _ = run_cli(["portfolio", "--permutations", "3", "--data-dir", str(tmp_path),
                            "--markets", "EURUSD,GOLD,SP500", "--strategy", "macd"])
    assert code == 0
    path = tmp_path / "portfolio.json"
    path.write_text(out)

    text = build_summary(portfolio=path)

    for part in ("## Multi-market portfolio", "equal-weight basket",
                 "Profit by market", "Cost stress", "| Max leverage |",
                 "Largest daily moves"):
        assert part in text
    report = {"ranking": [{"strategy": "x", "out_of_sample": {"sharpe": 0.9}}],
              "equal_weight_basket_out_of_sample": {"sharpe": 0.4}}
    assert "Best out-of-sample: x" in portfolio_verdict(report)
    report["equal_weight_basket_out_of_sample"]["sharpe"] = 1.2
    assert "No evidence" in portfolio_verdict(report)
    report["equal_weight_basket_out_of_sample"]["sharpe"] = 0.4
    report["ranking"][0]["p_value_adjusted"] = 0.6
    assert "diversification and leverage" in portfolio_verdict(report)
    report["ranking"][0]["p_value_adjusted"] = 0.01
    assert "preliminary evidence" in portfolio_verdict(report)


def test_in_currency_converts_each_date_at_the_latest_rate():
    from src.bnd.portfolio import currency_metrics, in_currency

    fx = [Candle(START + timedelta(days=i), r, r, r, r, 1)
          for i, r in enumerate((1.0, 1.25, 1.25))]
    curve = [(START, 100.0), (START + timedelta(days=1, hours=5), 100.0),
             (START + timedelta(days=5), 125.0)]

    converted = in_currency(curve, fx)

    # A flat USD account loses 20% for a EUR investor when EUR rises 25%.
    assert [round(v, 6) for _, v in converted] == [100.0, 80.0, 100.0]
    assert currency_metrics(curve, fx)["total_return_pct"] == pytest.approx(0.0)
    assert currency_metrics(curve, fx, initial_equity=125.0)["total_return_pct"] == \
        pytest.approx(-20.0)
    with pytest.raises(ValueError, match="No exchange rate"):
        in_currency([(START - timedelta(days=1), 1.0)], fx)


def test_portfolio_base_currency_eur(tmp_path):
    from src.bnd.backtest_summary import build_summary

    write_markets(tmp_path, ["GOLD", "SP500"])
    args = ["portfolio", "--permutations", "0", "--data-dir", str(tmp_path),
            "--markets", "GOLD,SP500", "--strategy", "macd", "--base-currency", "EUR"]
    code, _, err = run_cli(args)
    assert code == 2 and "EURUSD.csv" in err

    write_markets(tmp_path, ["EURUSD"])
    code, out, _ = run_cli(args)

    assert code == 0
    report = json.loads(out)
    assert report["base_currency"] == "EUR"
    assert "sharpe" in report["ranking"][0]["out_of_sample_base_currency"]
    assert "total_return_pct" in report["equal_weight_basket_out_of_sample_base_currency"]
    path = tmp_path / "portfolio.json"
    path.write_text(out)
    assert "**In EUR, unhedged**" in build_summary(portfolio=path)


def test_portfolio_combo_reports_what_each_member_adds(tmp_path):
    from src.bnd.backtest_summary import build_summary

    write_markets(tmp_path, ["EURUSD", "GOLD", "SP500"])
    code, out, _ = run_cli(["portfolio", "--permutations", "0", "--data-dir", str(tmp_path),
                            "--markets", "EURUSD,GOLD,SP500", "--strategy", "combo",
                            "--members", "macd,rsi_reversion,momentum"])

    assert code == 0
    report = json.loads(out)
    rows = report["ranking"][0]["combo_attribution_out_of_sample"]
    assert [r["strategy"] for r in rows] == ["macd", "rsi_reversion", "momentum"]
    assert all("sharpe" in r["alone"] and "sharpe" in r["combo_without_it"] for r in rows)
    path = tmp_path / "portfolio.json"
    path.write_text(out)
    assert "What each combo member adds" in build_summary(portfolio=path)
