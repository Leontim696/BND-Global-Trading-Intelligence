"""Plasa de siguranță pentru rulările zilnice întârziate de GitHub (16.11.2026)."""
from datetime import datetime, timezone
from pathlib import Path

from src.bnd import catchup as cu


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def run(created, status="completed", conclusion="success"):
    return {"createdAt": created, "status": status, "conclusion": conclusion}


EMPTY = {name: [] for name in cu.files()}


def names(out):
    return [n for n, _ in out]


def test_council_is_started_after_its_time_plus_grace_and_only_once():
    assert "consiliu-umbra.yml" not in names(cu.plan(EMPTY, at("2026-11-16T22:05:00")))
    out = cu.plan(EMPTY, at("2026-11-16T22:40:00"))
    assert ("consiliu-umbra.yml", {"mode": "daily"}) in out
    runs = dict(EMPTY, **{"consiliu-umbra.yml": [run("2026-11-16T22:41:00Z", "in_progress", None)]})
    assert "consiliu-umbra.yml" not in names(cu.plan(runs, at("2026-11-16T23:40:00")))


def test_a_run_from_last_night_does_not_count_for_today():
    runs = dict(EMPTY, **{"consiliu-umbra.yml": [run("2026-11-16T01:20:00Z")]})
    assert "consiliu-umbra.yml" in names(cu.plan(runs, at("2026-11-16T22:40:00")))


def test_accounts_wait_for_a_successful_council_today():
    late = at("2026-11-16T23:40:00")
    assert "cont-unic.yml" not in names(cu.plan(EMPTY, late))
    failed = dict(EMPTY, **{"consiliu-umbra.yml": [run("2026-11-16T22:41:00Z", conclusion="failure")]})
    assert "cont-unic.yml" not in names(cu.plan(failed, late))
    ok = dict(EMPTY, **{"consiliu-umbra.yml": [run("2026-11-16T22:41:00Z")]})
    out = names(cu.plan(ok, late))
    assert {"cont-unic.yml", "cont-control.yml", "formatii-ai.yml"} <= set(out)


def test_missing_run_list_never_triggers_a_start():
    runs = {k: v for k, v in EMPTY.items() if k != "consiliu-umbra.yml"}
    assert "consiliu-umbra.yml" not in names(cu.plan(runs, at("2026-11-16T22:40:00")))


def test_morning_jobs_and_status():
    out = names(cu.plan(EMPTY, at("2026-11-16T07:00:00")))
    assert {"dimineata.yml", "health-check.yml", "date-macro.yml", "status.yml"} <= set(out)
    recent = dict(EMPTY, **{"status.yml": [run("2026-11-16T06:10:00Z")]})
    assert "status.yml" not in names(cu.plan(recent, at("2026-11-16T07:00:00")))


def test_test_only_jobs_stop_after_30_november():
    out = names(cu.plan(EMPTY, at("2026-12-01T23:50:00")))
    assert "consiliu-umbra.yml" not in out and "cont-unic.yml" not in out


def test_cli_prints_dispatch_fields(tmp_path, capsys):
    for name in cu.files():
        (tmp_path / f"{name}.json").write_text("[]", encoding="utf-8")
    assert cu.main(["--runs-dir", str(tmp_path), "--now", "2026-11-16T22:40:00Z"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "consiliu-umbra.yml -f inputs[mode]=daily" in lines


def test_workflows_wire_the_safety_net():
    loop = Path(".github/workflows/preturi-live.yml").read_text(encoding="utf-8")
    assert "py -m src.bnd.catchup --runs-dir out/cu" in loop and "py -m src.bnd.catchup --list" in loop
    council = Path(".github/workflows/consiliu-umbra.yml").read_text(encoding="utf-8")
    assert "options: [mock, live, daily]" in council
    assert '[ "$EVENT" = schedule ] || [ "$MODE_INPUT" = daily ]' in council
    assert '[ "$EVENT" = schedule ] && [ "$(date -u +%H)" -lt 20 ]' in council
    for name in cu.files():
        assert "workflow_dispatch:" in Path(".github/workflows/" + name).read_text(encoding="utf-8"), name
