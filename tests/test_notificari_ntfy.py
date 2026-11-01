"""Ce merită o notificare pe telefon (ntfy) și cum se evită spamul."""

import json
from datetime import datetime, timedelta, timezone

from src.bnd import alerting, dashboard, smart_alerts

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def account(**kw):
    base = {"exists": True, "title": "Cont unic", "key": "unic", "kill_switch": False, "kill_reason": None,
            "reconciled": True, "last_run": NOW.isoformat(), "drawdown_pct": 0.0}
    return {**base, **kw}


def test_drawdown_alert_only_for_active_accounts_over_the_threshold():
    assert not dashboard.alerts_from([account(drawdown_pct=4.9)], [], NOW)
    found = dashboard.alerts_from([account(drawdown_pct=6.2)], [], NOW)
    assert found == ["Cont unic: scădere de 6.2% față de vârf"]
    assert not dashboard.alerts_from([account(key="paper", drawdown_pct=30.0)], [], NOW)      # cont arhivat


def test_failed_scheduled_collectors_are_reported_but_manual_runs_are_not():
    runs = [{"workflowName": "Date macro și context (arhivă)", "event": "schedule", "conclusion": "failure",
             "createdAt": "2026-11-02T06:20:00Z"},
            {"workflowName": "Smart-Money (colector walleturi)", "event": "workflow_dispatch", "conclusion": "failure",
             "createdAt": "2026-11-02T07:00:00Z"}]
    found = dashboard.alerts_from([], runs, NOW)
    assert found == ["Ultima rulare programată a colectării de date macro a eșuat (failure)"]


def test_smart_alerts_flag_repeated_winners_and_filter_passers(tmp_path):
    path = tmp_path / "d.csv"
    path.write_text("id,time,wallet,passes\n"
                    "a,2026-11-01T07:00+00:00,AAAAAAAAWalletRepeatedXXXXXXXXXXXXXXXXXXXX1234,0\n"
                    "b,2026-11-02T07:00+00:00,AAAAAAAAWalletRepeatedXXXXXXXXXXXXXXXXXXXX1234,0\n"
                    "c,2026-11-02T07:00+00:00,BBBBBBBBPasserXXXXXXXXXXXXXXXXXXXXXXXXXXXXX9999,1\n"
                    "d,2026-11-02T07:00+00:00,CCCCCCCCSingleXXXXXXXXXXXXXXXXXXXXXXXXXXXXX0000,0\n")
    found = smart_alerts.alerts_from(path)
    assert len(found) == 2
    assert "reapărut câștigător în 2 zile diferite" in found[0] and "AAAAAA…1234" in found[0]
    assert "trece toate filtrele" in found[1] and "BBBBBB…9999" in found[1]
    assert smart_alerts.alerts_from(tmp_path / "lipsa.csv") == []


def test_once_alerts_are_sent_exactly_once_and_survive_resolved_state(tmp_path):
    sent = []
    sender = lambda topic, title, message, priority: sent.append((title, message))
    state, extra, status = tmp_path / "s.json", tmp_path / "e.json", tmp_path / "st.json"
    status.write_text(json.dumps({"alerts": []}))
    extra.write_text(json.dumps({"once": ["Smart-Money: walletul X a reapărut"]}))
    import os
    os.environ["NTFY_TOPIC"] = "topic-de-proba-1234"
    try:
        assert alerting.main(["--status", str(status), "--state", str(state), "--extra", str(extra)], sender=sender) == 0
        assert alerting.main(["--status", str(status), "--state", str(state), "--extra", str(extra)], sender=sender) == 0
    finally:
        del os.environ["NTFY_TOPIC"]
    assert len(sent) == 1 and "walletul X" in sent[0][1]                     # a doua rulare nu mai trimite
    assert any(k.startswith("o:") for k in json.loads(state.read_text()))


def test_regular_alerts_still_repeat_after_the_cooldown_and_do_not_erase_once_keys():
    state = {"o:abc": NOW.isoformat()}
    fresh, new_state = alerting.once_due(["nou"], state, NOW)
    assert fresh == ["nou"] and "o:abc" in new_state
    due, _ = alerting.due(["x"], {}, NOW)
    assert due == ["x"]
