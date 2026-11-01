"""ntfy și jurnalul de audit cu lanț de hash-uri, fără rețea."""

import io
import json
from datetime import datetime, timezone

import pytest

from src.bnd import audit_log, notify

T0 = datetime(2026, 11, 1, tzinfo=timezone.utc)


class Reply(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_ntfy_sends_utf8_json_to_the_topic():
    seen = {}

    def opener(request, timeout):
        seen.update(json.loads(request.data), url=request.full_url)
        return Reply()

    notify.send("bnd-abcdef123456", "Alertă: oprire", "Pierdere mare ăâîșț", "high", opener=opener)

    assert seen == {"topic": "bnd-abcdef123456", "title": "Alertă: oprire",
                    "message": "Pierdere mare ăâîșț", "priority": 4, "url": "https://ntfy.sh"}


@pytest.mark.parametrize("kwargs", [dict(topic="x"), dict(topic="bnd abcdef123"),
                                    dict(topic="bnd-abcdef123456", server="http://ntfy.sh"),
                                    dict(topic="bnd-abcdef123456", priority="panica")])
def test_ntfy_refuses_bad_input(kwargs):
    args = {"topic": "bnd-abcdef123456", "title": "t", "message": "m", **kwargs}

    with pytest.raises(notify.NotifyError):
        notify.send(**args, opener=lambda *a, **k: Reply())


def test_ntfy_failure_is_a_clear_error_and_no_topic_is_silent(monkeypatch, capsys):
    def down(request, timeout):
        raise notify.URLError("jos")

    with pytest.raises(notify.NotifyError, match="nu poate fi contactat"):
        notify.send("bnd-abcdef123456", "t", "m", opener=down)
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert notify.main(["--title", "t", "--message", "m"]) == 0
    assert "nu se trimite" in capsys.readouterr().out
    monkeypatch.setenv("NTFY_TOPIC", "scurt")
    assert notify.main(["--title", "t", "--message", "m"]) == 2


def test_audit_chain_detects_edits_deletions_and_reordering(tmp_path):
    path = tmp_path / "audit.jsonl"
    for i in range(4):
        audit_log.append(path, "rulare", {"zi": i, "cost": 0.3}, T0)
    assert audit_log.verify(path)[0]

    lines = path.read_text(encoding="utf-8").splitlines()
    edited = json.loads(lines[1])
    edited["data"]["cost"] = 0.0
    path.write_text("\n".join([lines[0], json.dumps(edited), *lines[2:]]) + "\n", encoding="utf-8")
    ok, message = audit_log.verify(path)
    assert not ok and "Rândul 2" in message and "modificat" in message

    path.write_text("\n".join([lines[0], *lines[2:]]) + "\n", encoding="utf-8")   # rând șters
    ok, message = audit_log.verify(path)
    assert not ok and "lanțul e rupt" in message

    path.write_text("\n".join([lines[1], lines[0], *lines[2:]]) + "\n", encoding="utf-8")
    assert not audit_log.verify(path)[0]


def test_audit_log_appends_across_runs_and_cli(tmp_path, capsys):
    path = tmp_path / "audit.jsonl"
    audit_log.append(path, "a", {}, T0)
    second = audit_log.append(path, "b", {"x": 1}, T0)

    assert second["previous"] == json.loads(path.read_text().splitlines()[0])["hash"]
    assert audit_log.main(["verify", str(path)]) == 0
    assert audit_log.main(["verify", str(tmp_path / "lipsa.jsonl")]) == 1      # lipsă = problemă, nu "corect"
    path.write_text("nu e json\n", encoding="utf-8")
    assert audit_log.main(["verify", str(path)]) == 1 and audit_log.main([]) == 2
    capsys.readouterr()


def test_runs_append_to_the_audit_log(tmp_path, monkeypatch, capsys):
    from src.bnd import council_daily, paper_runner
    from tests.test_multi_market_cli import write_markets
    from tests.test_paper_runner import MARKETS, make_data, write_data

    write_markets(tmp_path, list(council_daily.DEFAULT_MARKETS), days=300)
    audit = tmp_path / "audit.jsonl"
    assert council_daily.main(["--data-dir", str(tmp_path), "--registry", str(tmp_path / "r.sqlite"),
                               "--audit-log", str(audit)]) == 0

    monkeypatch.setattr(paper_runner, "select_markets", lambda *a: MARKETS)
    write_data(tmp_path / "data", make_data())
    assert paper_runner.main(["--state", str(tmp_path / "p.sqlite"), "--data-dir",
                              str(tmp_path / "data"), "--capital", "1000",
                              "--audit-log", str(audit)]) == 0
    capsys.readouterr()

    rows = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert [r["kind"] for r in rows] == ["council_run", "daily_run"]
    assert rows[0]["data"]["decided"] == 10 and rows[0]["data"]["mode"] == "mock"
    assert rows[1]["data"]["kill_switch"] is False
    assert audit_log.verify(audit)[0]


def test_verify_treats_a_missing_or_empty_journal_as_a_problem_unless_first_run(tmp_path):
    from src.bnd import audit_log
    missing = tmp_path / "nu_exista.jsonl"
    assert audit_log.verify(missing) == (False, "Jurnalul lipsește.")
    assert audit_log.verify(missing, allow_missing=True)[0]
    empty = tmp_path / "gol.jsonl"
    empty.write_text("")
    assert audit_log.verify(empty) == (False, "Jurnalul e gol.")        # fără UnboundLocalError
    assert audit_log.verify(empty, allow_missing=True)[0]
    audit_log.append(tmp_path / "ok.jsonl", "x", {})
    assert audit_log.verify(tmp_path / "ok.jsonl")[0]
