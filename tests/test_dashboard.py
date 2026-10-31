"""Datele aplicației de pe telefon: doar citire, fără rețea."""

from datetime import datetime, timezone

import pytest

from src.bnd import dashboard
from src.bnd.paper_engine import PaperEngine

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


def test_missing_accounts_are_reported_not_fatal(tmp_path):
    data = dashboard.collect(tmp_path, None, None, tmp_path, NOW)

    assert [a["exists"] for a in data["accounts"]] == [False, False, False]
    assert data["council"] == {"exists": False}


def test_existing_account_is_summarised(tmp_path):
    PaperEngine.create(tmp_path / "paper.sqlite", 5_000.0, currency="USD", now=NOW).close()

    data = dashboard.collect(tmp_path, None, None, None, NOW)

    account = data["accounts"][0]
    assert account["exists"] and account["equity"] == 5_000.0
    assert account["positions"] == [] and account["kill_switch"] is False


def test_render_puts_data_in_the_template_and_escapes_script_ends():
    html = dashboard.render({"x": "</script>"}, "<script>const D = /*DATA*/null;</script>")

    assert "</script>\"" not in html.split("const D = ")[1]
    with pytest.raises(ValueError):
        dashboard.render({}, "fără loc pentru date")


def test_real_template_has_the_data_slot():
    from pathlib import Path
    assert "/*DATA*/null" in (Path(dashboard.__file__).parent / "dashboard_template.html").read_text(encoding="utf-8")


def test_live_prices_change_the_valuation_and_alerts_are_listed(tmp_path):
    from datetime import timedelta
    from src.bnd.paper_engine import Instrument, OrderRequest
    from src.bnd.market_data import Candle

    def candle(time, o, h, l, c):
        return Candle(time, o, h, l, c, 1000)

    engine = PaperEngine.create(tmp_path / "paper.sqlite", 10_000.0, currency="USD", now=NOW)
    engine.register_instrument(Instrument(symbol="AAA", asset_class="index", fee_pct=0, slippage_pct=0))
    engine.on_bar("AAA", candle(NOW - timedelta(days=1), 100, 101, 99, 100))
    engine.submit_order(OrderRequest("o1", "AAA", "BUY", 10, stop_loss=90), NOW)
    engine.on_bar("AAA", candle(NOW, 100, 101, 99, 100))
    engine.record("daily_run", {"time": (NOW - timedelta(hours=50)).isoformat(), "equity": 10_000.0}, NOW)
    engine.close()

    data = dashboard.collect(tmp_path, None, None, None, NOW,
                             quotes={"time": NOW.isoformat(), "quotes": {"AAA": [110.0, NOW.isoformat()]}},
                             runs=[{"workflowName": "Bot virtual zilnic", "event": "schedule",
                                    "conclusion": "failure", "createdAt": "2026-10-31T05:00:00Z"}])

    account = data["accounts"][0]
    assert account["live"] and account["live_equity"] > account["equity"]
    assert any("mai veche" in a for a in data["alerts"])
    assert any("a eșuat" in a for a in data["alerts"])


def test_quotes_snapshot_collects_names_and_times():
    from src.bnd import quotes_snapshot
    seen = []

    def fetch(symbol):
        seen.append(symbol)
        return 12.5, NOW

    result = quotes_snapshot.snapshot(fetch)

    assert result["quotes"]["BITCOIN"] == [12.5, NOW.isoformat()]
    assert "SPY" in seen and "SOL-USD" in seen


def test_remaining_budget_starts_at_the_owners_confirmed_figure(tmp_path):
    import sqlite3
    db = sqlite3.connect(tmp_path / "costs.sqlite")
    db.execute("CREATE TABLE usage_records (id INTEGER PRIMARY KEY, agent TEXT, model TEXT,"
               " input_tokens INT, output_tokens INT, cost_usd TEXT, timestamp TEXT)")
    db.execute("INSERT INTO usage_records (cost_usd, timestamp) VALUES ('0.2838356', '2026-10-31T09:00:00+00:00')")
    db.commit()
    assert dashboard.read_costs(tmp_path)["remaining"] == 8.05
    db.execute("INSERT INTO usage_records (cost_usd, timestamp) VALUES ('0.25', '2026-11-01T22:00:00+00:00')")
    db.commit()
    db.close()
    assert dashboard.read_costs(tmp_path)["remaining"] == pytest.approx(7.80)


def test_low_key_balance_raises_an_alert(tmp_path):
    import sqlite3
    (tmp_path / "registry.sqlite").write_bytes(b"")
    from src.bnd.decision_registry import DecisionRegistry
    (tmp_path / "registry.sqlite").unlink()
    DecisionRegistry(tmp_path / "registry.sqlite")
    db = sqlite3.connect(tmp_path / "costs.sqlite")
    db.execute("CREATE TABLE usage_records (id INTEGER PRIMARY KEY, agent TEXT, model TEXT,"
               " input_tokens INT, output_tokens INT, cost_usd TEXT, timestamp TEXT)")
    db.execute("INSERT INTO usage_records (cost_usd, timestamp) VALUES ('7', '2026-11-10T09:00:00+00:00')")
    db.commit(); db.close()

    data = dashboard.collect(None, None, None, tmp_path, NOW)

    assert any("Soldul cheii" in a for a in data["alerts"])
