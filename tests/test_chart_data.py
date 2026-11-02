"""Datele pentru graficele și panoul X-Ray al aplicației: compacte, doar citire, fără surse duplicate."""
from datetime import datetime, timedelta, timezone

from src.bnd import chart_data, dashboard
from src.bnd.market_data import Candle, save_csv

START = datetime(2026, 6, 1, tzinfo=timezone.utc)


def write(folder, name, n, base=100.0, step=1):
    folder.mkdir(parents=True, exist_ok=True)
    save_csv([Candle(START + timedelta(days=i * step), base, base * 2, base * .5, base * (1 + i / 1000), 1234.5678)
              for i in range(n)], folder / f"{name}.csv")


def test_candles_are_compact_rounded_and_keep_the_gaps_between_days(tmp_path):
    write(tmp_path / "zilnic", "SP500", 200, step=1)
    write(tmp_path / "zilnic", "GOLD", 10, step=3)                  # zile lipsă (weekend, sărbători) se păstrează

    data = chart_data.candles([tmp_path / "zilnic"], bars=120)

    assert len(data["SP500"]["c"]) == 120 and data["SP500"]["d"][0] == 0
    assert data["GOLD"]["d"] == [0, 3, 6, 9, 12, 15, 18, 21, 24, 27]
    assert data["SP500"]["v"][0] == 1230.0                          # volum cu 3 cifre semnificative


def test_long_names_win_over_top50_duplicates(tmp_path):
    write(tmp_path / "zilnic", "BITCOIN", 5, base=70000)
    write(tmp_path / "crypto50", "BTC", 5, base=1)                  # aceeași monedă din arhiva top 50
    write(tmp_path / "crypto50", "PEPE", 5, base=5e-06)

    data = chart_data.candles([tmp_path / "zilnic", tmp_path / "crypto50"])

    assert set(data) == {"BITCOIN", "PEPE"} and data["BITCOIN"]["c"][0] == 70000.0
    assert data["PEPE"]["c"][0] == 5e-06                            # prețurile mici nu se pierd la rotunjire


def test_missing_or_broken_files_are_skipped(tmp_path):
    (tmp_path / "z").mkdir()
    (tmp_path / "z" / "BAD.csv").write_text("nu e csv")
    assert chart_data.candles([tmp_path / "z", tmp_path / "lipsa"]) == {}


def test_reasons_come_from_the_day_report_with_latest_as_fallback(tmp_path):
    report = ("## BITCOIN: **VINDE** (înclină spre vânzare)\n"
              "Preț 70000.0000 (închidere 2026-10-30); regula simplă a botului: vinde; cost 0.027 $.\n\n"
              "| Agent | Vot | Încredere | Motiv |\n|---|---|---:|---|\n"
              "| gpt | SELL | 0.6 | Trend descendent \\| RSI scăzut |\n| claude | HOLD | 0.4 | " + "x" * 600 + " |\n")
    (tmp_path / "LATEST.md").write_text(report, encoding="utf-8")

    reasons = chart_data.council_reasons(tmp_path, "2026-11-02")       # nu există fișierul zilei: se ia LATEST

    assert reasons["BITCOIN"]["gpt"] == "Trend descendent | RSI scăzut"
    assert len(reasons["BITCOIN"]["claude"]) == chart_data.REASON_CHARS
    assert chart_data.council_reasons(None, "2026-11-02") == {}


def test_collect_carries_charts(tmp_path):
    write(tmp_path / "zilnic", "SP500", 30)
    data = dashboard.collect(None, None, None, None, charts=[tmp_path / "zilnic"])
    assert list(data["charts"]) == ["SP500"]
