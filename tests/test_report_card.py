"""Raportul în română despre contul virtual."""

import json
from datetime import datetime, timedelta, timezone

from src.bnd import report_card
from src.bnd.paper_engine import PaperEngine
from src.bnd.paper_runner import run_daily
from tests.test_paper_runner import MARKETS, START, config, factory, make_data, now_after


def account_with_positions(tmp_path):
    data = make_data(121)
    today = {name: candles[:-1] for name, candles in data.items()}
    path = tmp_path / "paper.sqlite"
    engine = PaperEngine.create(path, 10_000, currency="EUR", now=START)
    run_daily(engine, today, MARKETS, factory, config(), "sma", now_after(today))
    run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))
    held = {p["symbol"]: engine.mark(p["symbol"])["price"] for p in engine.positions()}
    engine.close()
    return path, now_after(data), held


def test_no_account_is_explained(tmp_path):
    report = report_card.build(tmp_path / "none.sqlite", START)

    text = report_card.render(report)
    assert not report["has_account"] and "nu există încă" in text


def test_live_prices_change_the_value_now_but_not_the_close(tmp_path):
    path, now, held = account_with_positions(tmp_path)
    plain = report_card.build(path, now)
    quotes = {name: (price * 1.10, now) for name, price in held.items()}

    live = report_card.build(path, now, quotes)

    assert plain["equity_now"] == plain["equity_close"]
    assert live["equity_close"] == plain["equity_close"]
    assert live["equity_now"] != plain["equity_close"]
    assert live["live_prices"] == len(held) > 0
    moved = {p["market"]: p["change_today_pct"] for p in live["positions"]}
    assert all(abs(v - 10) < 1e-6 for v in moved.values())


def test_rendered_report_is_plain_romanian_with_the_key_numbers(tmp_path):
    path, now, held = account_with_positions(tmp_path)
    early = START + timedelta(days=2, hours=5)            # ziua 3 a contului
    report = report_card.build(path, early, {n: (p, early) for n, p in held.items()})

    text = report_card.render(report)

    for part in ("# Raport bot virtual", "Ziua 3 din 16", "Valoarea contului acum",
                 "Oprirea de siguranță", "## Pozițiile", "Bani virtuali"):
        assert part in text
    assert "ACTIVĂ" not in text


def test_after_sixteen_days_the_report_says_the_test_is_over(tmp_path):
    path, now, _ = account_with_positions(tmp_path)

    text = report_card.render(report_card.build(path, START + timedelta(days=20)))

    assert "s-a încheiat" in text and "Ziua 21 din 16" not in text


def test_kill_switch_and_problems_are_shown(tmp_path):
    path, now, _ = account_with_positions(tmp_path)
    engine = PaperEngine.open(path)
    with engine._transaction():
        engine._trip("test", now.isoformat())
    engine.close()

    text = report_card.render(report_card.build(path, now + timedelta(hours=80)))

    assert "ACTIVĂ" in text and "## Atenție" in text and "nu a mai rulat" in text


def test_quotes_only_for_known_markets_and_failures_are_skipped():
    calls = []

    def fake(symbol):
        calls.append(symbol)
        return None if symbol == "GLD" else (123.0, START)

    found = report_card.quotes_for(["GOLD", "SP500", "NU_EXISTA"], fake)

    assert "NU_EXISTA" not in found and "GOLD" not in found      # GLD a dat None
    assert found["SP500"] == (123.0, START)
    assert len(calls) == 2


def test_cli_writes_markdown_and_json(tmp_path, capsys):
    path, _, _ = account_with_positions(tmp_path)
    out, as_json = tmp_path / "r.md", tmp_path / "r.json"

    assert report_card.main(["--state", str(path), "--out", str(out), "--json", str(as_json),
                             "--no-live"]) == 0
    assert "# Raport bot virtual" in out.read_text(encoding="utf-8")
    assert json.loads(as_json.read_text())["has_account"] is True
    capsys.readouterr()
