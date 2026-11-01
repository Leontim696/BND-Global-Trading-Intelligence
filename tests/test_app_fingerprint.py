import json
import sqlite3
from datetime import datetime, timedelta, timezone

from src.bnd import app_fingerprint as fp

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def db(path, positions=0):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE positions (symbol TEXT)")
    for i in range(positions):
        conn.execute("INSERT INTO positions VALUES (?)", (f"S{i}",))
    conn.commit(); conn.close()
    return path


def test_unchanged_inputs_give_the_same_fingerprint_and_a_change_alters_it(tmp_path):
    unic = db(tmp_path / "u.sqlite")
    balance = tmp_path / "b.json"
    balance.write_text(json.dumps({"effective_remaining": 36.4162, "time": "10:35"}))
    a = fp.fingerprint(unic, tmp_path, balance)
    balance.write_text(json.dumps({"effective_remaining": 36.4163, "time": "11:35"}))     # doar timpul și o fracțiune de cent
    assert fp.fingerprint(unic, tmp_path, balance) == a
    balance.write_text(json.dumps({"effective_remaining": 33.90}))
    assert fp.fingerprint(unic, tmp_path, balance) != a
    (tmp_path / "registry.sqlite").write_bytes(b"x")                                          # consiliu nou
    assert fp.fingerprint(unic, tmp_path, balance) != fp.fingerprint(unic, tmp_path / "gol", balance)


def test_quotes_only_matter_when_there_are_open_positions(tmp_path):
    flat = db(tmp_path / "f.sqlite", 0)
    held = db(tmp_path / "h.sqlite", 2)
    q = tmp_path / "q.json"
    q.write_text("{\"a\": 1}")
    flat_a, held_a = fp.fingerprint(flat, quotes=q), fp.fingerprint(held, quotes=q)
    q.write_text("{\"a\": 2}")
    assert fp.fingerprint(flat, quotes=q) == flat_a and fp.fingerprint(held, quotes=q) != held_a


def test_new_failed_run_or_alert_changes_the_fingerprint(tmp_path):
    runs = tmp_path / "r.json"
    runs.write_text(json.dumps([{"workflowName": "Cont unic", "conclusion": "success"}]))
    ok = fp.fingerprint(runs=runs)
    runs.write_text(json.dumps([{"workflowName": "Cont unic", "conclusion": "failure"}]))
    assert fp.fingerprint(runs=runs) != ok
    alerts = tmp_path / "a.json"
    alerts.write_text(json.dumps({"sent": ["x"]}))
    assert fp.fingerprint(runs=runs, alerts=alerts) != fp.fingerprint(runs=runs)


def test_refresh_decision_with_heartbeat():
    assert fp.needs_refresh("a", None, None, NOW) == (True, "prima publicare")
    assert fp.needs_refresh("b", "a", NOW.isoformat(), NOW)[0]
    same_recent = fp.needs_refresh("a", "a", (NOW - timedelta(hours=3)).isoformat(), NOW)
    assert same_recent == (False, "nimic nou")
    assert fp.needs_refresh("a", "a", (NOW - timedelta(hours=13)).isoformat(), NOW)[0]
    assert fp.needs_refresh("a", "a", "nu e dată", NOW)[0]


def test_cli_prints_json(tmp_path, capsys):
    assert fp.main(["--balance", str(tmp_path / "lipsa.json")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["refresh"] is True and len(out["fingerprint"]) == 16
