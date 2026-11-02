"""Ce merită o notificare pe telefon (ntfy) și cum se evită spamul."""

import json
from datetime import datetime, timezone

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


def test_events_report_first_fills_big_daily_moves_council_summary_and_test_end():
    unic = account(fills=3, positions=[1, 2], currency="USD",
                   history=[{"t": "2026-11-02T22:00:00+00:00", "equity": 11000.0},
                            {"t": "2026-11-03T22:00:00+00:00", "equity": 11330.0}])
    council = {"exists": True, "day": "2026-11-03", "markets": [1] * 88, "costs": {"today": 2.41, "remaining": 33.5}}
    events = dashboard.events_from([unic], council, datetime(2026, 11, 3, 23, tzinfo=timezone.utc))
    assert "Cont unic: s-au executat primele ordine (2 poziții deschise)" in events
    assert any(e.startswith("Cont unic: variație zilnică +3.0%") and e.endswith("la 2026-11-03") for e in events)
    assert "Consiliul AI 2026-11-03: 88 piețe votate, cost azi 2.41 $, rămas 33.50 $" in events
    assert not any("încheiat" in e for e in events)
    end = dashboard.events_from([], None, datetime(2026, 11, 16, 8, tzinfo=timezone.utc))
    assert end == ["Testul de 16 zile s-a încheiat: raportul final urmează (17.11)"]


def test_small_moves_archived_accounts_and_missing_data_produce_no_events():
    quiet = account(fills=0, positions=[], currency="USD",
                    history=[{"t": "a", "equity": 100.0}, {"t": "2026-11-03T22:00:00+00:00", "equity": 101.0}])
    old = account(key="paper", fills=9, positions=[1], currency="USD", history=[])
    assert dashboard.events_from([quiet, old, {"exists": False}], {"exists": False}, NOW) == []


def test_events_in_status_json_are_sent_once_by_the_alerting_step(tmp_path):
    sent = []
    state, status = tmp_path / "s.json", tmp_path / "st.json"
    status.write_text(json.dumps({"alerts": [], "events": ["Cont unic: variație zilnică +3.0% (valoare 11,330 USD) la 2026-11-03"]}))
    import os
    os.environ["NTFY_TOPIC"] = "topic-de-proba-1234"
    try:
        for _ in range(2):
            alerting.main(["--status", str(status), "--state", str(state)],
                          sender=lambda topic, title, message, priority: sent.append(message))
    finally:
        del os.environ["NTFY_TOPIC"]
    assert len(sent) == 1 and "variație zilnică" in sent[0]
