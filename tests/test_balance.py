"""Soldul real OpenRouter: citire, alegerea valorii potrivite și folosirea ei în aplicație."""

import json
from datetime import datetime, timedelta, timezone

from src.bnd import dashboard, morning, openrouter_balance as ob

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def fake_get(path, key, timeout=20.0):
    assert key == "sk-test" and path in ("/key", "/credits")
    if path == "/key":
        return {"limit": 40.0, "usage": 2.1, "limit_remaining": 37.9}
    return {"total_credits": 40.0, "total_usage": 2.1}


def test_effective_balance_is_the_smaller_of_key_limit_and_account_credit():
    result = ob.read_balance("sk-test", fake_get)
    assert result["ok"] and result["effective_remaining"] == 37.9
    assert result["credits_remaining"] == 37.9 and "sk-test" not in json.dumps(result)

    def tighter(path, key, timeout=20.0):
        return ({"limit": 10.0, "usage": 2.0, "limit_remaining": 8.0} if path == "/key"
                else {"total_credits": 40.0, "total_usage": 2.0})
    assert ob.read_balance("k", tighter)["effective_remaining"] == 8.0      # plafonul cheii strânge


def test_a_failing_endpoint_still_uses_the_other_and_total_failure_is_marked(tmp_path):
    def only_credits(path, key, timeout=20.0):
        if path == "/key":
            raise ValueError("/key: URLError")
        return {"total_credits": 50.0, "total_usage": 5.0}
    result = ob.read_balance("k", only_credits)
    assert result["ok"] and result["effective_remaining"] == 45.0 and "key_error" in result

    def dead(path, key, timeout=20.0):
        raise ValueError(path + ": URLError")
    assert not ob.read_balance("k", dead)["ok"]
    assert ob.main(["--out", str(tmp_path / "b.json")], get=dead) == 0       # eșecul nu oprește workflow-ul


def test_missing_key_is_reported_without_crashing(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert ob.main(["--out", str(tmp_path / "b.json")]) == 0
    assert json.loads((tmp_path / "b.json").read_text())["ok"] is False


def costs_db(folder):
    import sqlite3
    db = sqlite3.connect(folder / "costs.sqlite")
    db.execute("CREATE TABLE usage_records (id INTEGER PRIMARY KEY, agent TEXT, model TEXT,"
               " input_tokens INT, output_tokens INT, cost_usd TEXT, timestamp TEXT)")
    db.execute("INSERT INTO usage_records (cost_usd, timestamp) VALUES ('0.5', '2026-11-01T01:00:00+00:00')")
    db.commit(); db.close()


def test_a_fresh_real_balance_replaces_the_estimate_and_a_top_up_shows_up(tmp_path):
    costs_db(tmp_path)
    estimate = dashboard.read_costs(tmp_path, None, NOW)
    assert estimate["source"] == "estimare" and abs(estimate["remaining"] - 37.8359) < 0.01

    fresh = {"ok": True, "time": (NOW - timedelta(minutes=30)).isoformat(), "effective_remaining": 77.9}
    real = dashboard.read_costs(tmp_path, fresh, NOW)
    assert real["source"] == "openrouter" and real["remaining"] == 77.9      # după o reîncărcare

    stale = {**fresh, "time": (NOW - timedelta(hours=20)).isoformat()}
    assert dashboard.read_costs(tmp_path, stale, NOW)["source"] == "estimare"
    assert dashboard.read_costs(tmp_path, {"ok": False}, NOW)["source"] == "estimare"
    future = {**fresh, "time": (NOW + timedelta(hours=3)).isoformat()}
    assert dashboard.read_costs(tmp_path, future, NOW)["source"] == "estimare"


def test_low_balance_alert_follows_the_real_value_and_the_morning_summary_names_the_source(tmp_path):
    from src.bnd.decision_registry import DecisionRegistry
    DecisionRegistry(tmp_path / "registry.sqlite")
    costs_db(tmp_path)
    low = {"ok": True, "time": NOW.isoformat(), "effective_remaining": 1.2}

    data = dashboard.collect(None, None, None, tmp_path, NOW, balance=low)
    assert any("Soldul cheii" in a for a in data["alerts"])

    ok = {"ok": True, "time": NOW.isoformat(), "effective_remaining": 77.9}
    text = morning.build(None, None, None, tmp_path, NOW, balance=ok)["message"]
    assert "77.90 $ (citit de la OpenRouter)" in text
