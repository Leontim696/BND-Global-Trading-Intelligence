"""Offline market-data and backtest CLI tests; never contact Binance."""

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from src.bnd import market_data
from src.bnd.backtest_cli import main
from src.bnd.market_data import (
    Candle,
    MarketDataError,
    fetch_binance_klines,
    load_csv,
    parse_binance_klines,
    save_csv,
)

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
STEP = timedelta(hours=4)


def kline(index, price=100.0):
    open_ms = int((START + STEP * index).timestamp() * 1000)
    return [open_ms, str(price), str(price + 1), str(price - 1),
            str(price + 0.5), "12.5", open_ms + 1, "0", 1, "0", "0", "0"]


def candles(count):
    return parse_binance_klines([kline(i, 100.0 + i) for i in range(count)])


class FakeResponse:
    def __init__(self, payload):
        self.raw = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, limit):
        return self.raw[:limit]


def test_parse_binance_klines():
    result = parse_binance_klines([kline(0)])

    assert result[0].open_time == START
    assert result[0].close == 100.5
    assert result[0].volume == 12.5


@pytest.mark.parametrize(
    "fields",
    [
        dict(open=0.0),
        dict(high=99.0),
        dict(low=101.0),
        dict(volume=-1.0),
        dict(close=float("nan")),
    ],
)
def test_invalid_candle_rejected(fields):
    values = dict(open_time=START, open=100.0, high=101.0, low=99.0,
                  close=100.0, volume=1.0)
    values.update(fields)

    with pytest.raises(MarketDataError):
        Candle(**values)


def test_naive_timestamp_rejected():
    with pytest.raises(MarketDataError):
        Candle(datetime(2024, 1, 1), 100, 101, 99, 100, 1)


def test_csv_round_trip(tmp_path):
    path = tmp_path / "data" / "btc.csv"
    original = candles(5)

    save_csv(original, path)

    assert load_csv(path) == original


def test_csv_rejects_duplicates(tmp_path):
    path = tmp_path / "btc.csv"
    save_csv(candles(3), path)
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines + [lines[-1]]) + "\n")

    with pytest.raises(MarketDataError, match="increasing"):
        load_csv(path)


def test_csv_reports_bad_line(tmp_path):
    path = tmp_path / "btc.csv"
    save_csv(candles(3), path)
    lines = path.read_text().splitlines()
    lines[2] = lines[2].replace("101", "abc", 1)
    path.write_text("\n".join(lines) + "\n")

    with pytest.raises(MarketDataError, match="line 3"):
        load_csv(path)


def test_fetch_paginates_and_drops_open_candle(monkeypatch):
    monkeypatch.setattr(market_data, "BINANCE_PAGE_LIMIT", 3)
    requests = []
    total = 7

    def fake_urlopen(request, timeout):
        query = parse_qs(urlparse(request.full_url).query)
        requests.append(query)
        start_ms = int(query["startTime"][0])
        first = next(
            i for i in range(total)
            if kline(i)[0] >= start_ms
        )
        return FakeResponse([kline(i) for i in range(first, min(first + 3, total))])

    monkeypatch.setattr(market_data, "urlopen", fake_urlopen)
    end = START + STEP * total

    result = fetch_binance_klines("btcusdt", "4h", START, end)

    assert len(requests) == 3
    assert requests[0]["symbol"] == ["BTCUSDT"]
    assert len(result) == total
    assert [c.open_time for c in result] == [START + STEP * i for i in range(total)]


def test_fetch_drops_candle_still_forming(monkeypatch):
    now = datetime.now(timezone.utc)
    start = now - STEP * 3

    def fake_urlopen(request, timeout):
        rows = []
        for i in range(3):
            row = kline(0)
            row[0] = int((start + STEP * i + STEP / 2).timestamp() * 1000)
            rows.append(row)
        return FakeResponse(rows)

    monkeypatch.setattr(market_data, "urlopen", fake_urlopen)

    result = fetch_binance_klines("BTCUSDT", "4h", start, now)

    assert len(result) == 2


def test_cli_run_reports_strategy_and_benchmark(tmp_path, capsys):
    path = tmp_path / "btc.csv"
    # Synthetic zig-zag trend, for plumbing only.
    prices = [100 + i * 0.5 + (5 if i % 10 < 5 else -5) for i in range(200)]
    save_csv(parse_binance_klines([kline(i, p) for i, p in enumerate(prices)]), path)

    code = main([
        "run", "--data", str(path), "--strategy", "sma_crossover",
        "--fast", "5", "--slow", "20", "--stop-loss", "5",
        "--risk-per-trade", "1",
    ])

    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert set(report["periods"]) == {"full", "in_sample", "out_of_sample"}
    for period in report["periods"].values():
        assert "total_return_pct" in period["strategy"]
        assert period["buy_and_hold"]["trades"] == 1


def test_cli_risk_requires_stop_loss(tmp_path, capsys):
    path = tmp_path / "btc.csv"
    save_csv(candles(50), path)

    code = main(["run", "--data", str(path), "--risk-per-trade", "1"])

    assert code == 2
    assert "stop loss" in capsys.readouterr().err


def test_cli_missing_file_is_clear_error(tmp_path, capsys):
    code = main(["run", "--data", str(tmp_path / "missing.csv")])

    assert code == 2
    assert "Cannot read" in capsys.readouterr().err


def test_find_gaps_reports_missing_candles():
    from src.bnd.market_data import find_gaps

    series = candles(6)
    gapped = series[:2] + series[4:]

    assert find_gaps(series) == []
    assert find_gaps(gapped) == [(series[1].open_time, series[4].open_time)]


def write_trend_csv(path, count=200):
    prices = [100 + i * 0.5 + (5 if i % 10 < 5 else -5) for i in range(count)]
    save_csv(parse_binance_klines([kline(i, p) for i, p in enumerate(prices)]), path)


def test_cli_refuses_to_run_without_risk_gate(tmp_path, capsys):
    path = tmp_path / "btc.csv"
    write_trend_csv(path)

    code = main(["run", "--data", str(path)])

    assert code == 2
    assert "--no-risk-gate" in capsys.readouterr().err


def test_cli_research_mode_is_labelled(tmp_path, capsys):
    path = tmp_path / "btc.csv"
    write_trend_csv(path)

    code = main(["run", "--data", str(path), "--no-risk-gate",
                 "--fast", "5", "--slow", "20"])

    assert code == 0
    report = json.loads(capsys.readouterr().out)
    for period in report["periods"].values():
        assert period["strategy"]["risk_gate"] == "disabled_research_only"


def test_cli_out_of_sample_starts_at_split_with_warm_up(tmp_path, capsys):
    path = tmp_path / "btc.csv"
    write_trend_csv(path)

    main(["run", "--data", str(path), "--no-risk-gate",
          "--fast", "5", "--slow", "20"])

    report = json.loads(capsys.readouterr().out)
    oos = report["periods"]["out_of_sample"]
    assert oos["start"] == (START + STEP * 140).isoformat()
    # Warm-up lets the benchmark (and strategy) trade from the first bar.
    assert oos["buy_and_hold"]["trades"] == 1


def test_cli_require_continuous_rejects_gaps(tmp_path, capsys):
    path = tmp_path / "btc.csv"
    series = candles(60)
    save_csv(series[:30] + series[31:], path)

    code = main(["run", "--data", str(path), "--no-risk-gate",
                 "--require-continuous"])

    assert code == 2
    assert "gaps" in capsys.readouterr().err


def test_to_bars_keeps_open_and_close():
    from src.bnd.market_data import to_bars

    series = candles(3)

    bars = to_bars(series)

    assert [(b.open, b.close) for b in bars] == [(c.open, c.close) for c in series]


def test_cli_walk_forward_reports_folds_with_times(tmp_path, capsys):
    path = tmp_path / "btc.csv"
    write_trend_csv(path, count=200)

    code = main(["walk-forward", "--data", str(path), "--window", "10",
                 "--train", "50", "--test", "50"])

    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["fold_count"] == 3
    first = report["folds"][0]
    assert first["test_start_time"] == (START + STEP * 50).isoformat()
    assert first["test_end_time"] == (START + STEP * 99).isoformat()
    # 4-hour candles -> about 2,192 periods per year.
    assert report["summary"]["periods_per_year"] == 2192


def test_cli_walk_forward_rejects_window_larger_than_train(tmp_path, capsys):
    path = tmp_path / "btc.csv"
    write_trend_csv(path, count=200)

    code = main(["walk-forward", "--data", str(path), "--window", "60",
                 "--train", "50", "--test", "50"])

    assert code == 2
    assert "window" in capsys.readouterr().err.lower()


def test_repair_spikes_fixes_reverting_bad_ticks_only():
    from src.bnd.market_data import repair_spikes

    def series(closes):
        return [Candle(START + STEP * i, c, c, c, c, 1) for i, c in enumerate(closes)]

    bad_tick = series([100, 101, 150, 102, 103])     # +48.5% then back
    crash = series([100, 101, 60, 58, 57])           # -40% that persists
    rebound = series([100, 101, 70, 95, 96])          # -31%, only 81% undone -> repaired
    partial = series([100, 101, 70, 80, 81])          # -31%, only 32% undone -> real

    fixed, repairs = repair_spikes(bad_tick)
    assert [c.close for c in fixed] == [100, 101, 101, 102, 103]
    assert repairs[0]["date"] == (START + STEP * 2).date().isoformat()
    assert repair_spikes(crash)[1] == []
    assert len(repair_spikes(rebound)[1]) == 1
    assert repair_spikes(partial)[1] == []
