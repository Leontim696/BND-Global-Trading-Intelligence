"""Alerte fără repetiții și verificarea restaurării: offline, fără notificări reale."""

import json
import shutil
from datetime import datetime, timedelta, timezone

from src.bnd import alerting, audit_log, restore_check
from src.bnd.paper_engine import PaperEngine

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def test_same_alert_is_sent_once_then_after_the_pause_and_resolved_ones_are_forgotten():
    fresh, state = alerting.due(["A", "A", "B"], {}, NOW)
    assert fresh == ["A", "B"]

    fresh, state = alerting.due(["A", "B"], state, NOW + timedelta(hours=1))
    assert fresh == []                                           # fără repetiție

    fresh, state = alerting.due(["A"], state, NOW + timedelta(hours=13))
    assert fresh == ["A"]                                        # persistă după pauză
    assert len(state) == 1                                       # B s-a rezolvat: uitată

    fresh, _ = alerting.due(["B"], state, NOW + timedelta(hours=14))
    assert fresh == ["B"]                                        # poate reapărea


def test_cli_sends_only_new_alerts_and_keeps_state_on_failure(tmp_path, monkeypatch):
    status = tmp_path / "status.json"
    status.write_text(json.dumps({"alerts": ["Cont oprit"]}))
    state = tmp_path / "state.json"
    sent = []
    monkeypatch.setenv("NTFY_TOPIC", "topic-secret-123")

    assert alerting.main(["--status", str(status), "--state", str(state)],
                         sender=lambda *a: sent.append(a)) == 0
    assert alerting.main(["--status", str(status), "--state", str(state)],
                         sender=lambda *a: sent.append(a)) == 0
    assert len(sent) == 1 and "Cont oprit" in sent[0][2]

    state.unlink()

    def failing(*args):
        raise alerting.notify.NotifyError("fără rețea")
    assert alerting.main(["--status", str(status), "--state", str(state)], sender=failing) == 1
    assert not state.exists()                                    # se reîncearcă data viitoare


def test_without_a_topic_nothing_is_sent_and_it_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    status = tmp_path / "s.json"
    status.write_text(json.dumps({"alerts": ["X"]}))
    assert alerting.main(["--status", str(status), "--state", str(tmp_path / "st.json")],
                         sender=lambda *a: (_ for _ in ()).throw(AssertionError("nu trebuia trimis"))) == 0


def make_backup(folder, tamper=False):
    folder.mkdir()
    source = folder / "src.sqlite"
    PaperEngine.create(source, 1_000.0, currency="USD", now=NOW).close()
    shutil.copy(source, folder / "paper_20261101_120000.sqlite")
    source.unlink()
    audit_log.append(folder / "audit_20261101_120000.jsonl", "a", {}, NOW)
    if tamper:
        path = folder / "audit_20261101_120000.jsonl"
        path.write_text(path.read_text().replace('"a"', '"b"'))


def test_a_good_backup_is_restorable(tmp_path):
    make_backup(tmp_path / "b")
    result = restore_check.check(tmp_path / "b")
    assert result["ok"] and result["audit_checked"]


def test_a_tampered_audit_or_empty_folder_or_garbage_copy_fails(tmp_path):
    make_backup(tmp_path / "b", tamper=True)
    assert not restore_check.check(tmp_path / "b")["ok"]
    (tmp_path / "e").mkdir()
    assert not restore_check.check(tmp_path / "e")["ok"]
    (tmp_path / "g").mkdir()
    (tmp_path / "g" / "paper_1.sqlite").write_bytes(b"nu e sqlite" * 50)
    assert not restore_check.check(tmp_path / "g")["ok"]
