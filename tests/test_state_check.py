"""Punctul de control al contului unic: nu se publică stare parțială sau stricată (audit 01.11, P0)."""
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.bnd import audit_log, state_check
from src.bnd.paper_engine import PaperEngine

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 2, 22, 25, tzinfo=timezone.utc)


def make_account(folder: Path, capital=10000.0):
    folder.mkdir(parents=True)
    engine = PaperEngine.create(folder / "paper.sqlite", capital, currency="USD", now=NOW)
    engine.close()
    audit_log.append(folder / "audit.jsonl", "daily_run",
                     {"equity": capital, "orders": 0, "kill_switch": False}, NOW)
    (folder / "last_run.json").write_text(json.dumps({"equity": capital}))


def run_day(folder: Path, equity=10100.0, *, audit=True, last=True):
    """Simulează pasul zilnic: jurnal nou în SQLite, rând nou în audit, last_run.json."""
    engine = PaperEngine.open(folder / "paper.sqlite")
    engine._log("nota", {"x": 1}, NOW)
    engine.close()
    if audit:
        audit_log.append(folder / "audit.jsonl", "daily_run",
                         {"equity": equity, "orders": 1, "kill_switch": False}, NOW)
    if last:
        (folder / "last_run.json").write_text(json.dumps({"equity": equity}))


@pytest.fixture
def days(tmp_path):
    prev, state = tmp_path / "prev", tmp_path / "state"
    make_account(prev)
    shutil.copytree(prev, state)
    return prev, state


def test_valid_run_passes_and_marker_verifies(days):
    prev, state = days
    run_day(state)
    assert state_check.check(state, prev) == []
    assert state_check.main(["--state", str(state), "--previous", str(prev)]) == 0
    done = subprocess.run(["bash", str(ROOT / "scripts/verify_marker.sh"), str(state)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


def test_crash_during_execution_is_rejected(days):
    """SQLite avansat, dar rularea nu a ajuns la audit/last_run: stare parțială."""
    prev, state = days
    run_day(state, audit=False, last=False)
    problems = state_check.check(state, prev)
    assert any("niciun rând nou" in p for p in problems)


def test_audit_written_but_last_run_stale_is_rejected(days):
    prev, state = days
    run_day(state, equity=10100.0, last=False)
    assert any("valori diferite" in p for p in state_check.check(state, prev))


def test_corrupt_sqlite_is_rejected(days):
    prev, state = days
    run_day(state)
    data = (state / "paper.sqlite").read_bytes()
    (state / "paper.sqlite").write_bytes(data[:len(data) // 2])
    assert state_check.check(state, prev)


def test_garbage_sqlite_is_rejected(days):
    prev, state = days
    run_day(state)
    (state / "paper.sqlite").write_bytes(b"nu e sqlite" * 100)
    assert state_check.check(state, prev)


def test_rewritten_audit_history_is_rejected(days):
    prev, state = days
    run_day(state)
    lines = (state / "audit.jsonl").read_text().splitlines()
    first = json.loads(lines[0])
    first["data"]["equity"] = 99999.0
    lines[0] = json.dumps(first, sort_keys=True)
    (state / "audit.jsonl").write_text("\n".join(lines) + "\n")
    problems = state_check.check(state, prev)
    assert any("audit.jsonl" in p for p in problems)


def test_replaced_account_is_rejected(days, tmp_path):
    prev, state = days
    shutil.rmtree(state)
    make_account(state, capital=5000.0)
    run_day(state)
    assert any("capitalul inițial" in p for p in state_check.check(state, prev))


def test_shrunken_history_is_rejected(days):
    prev, state = days
    run_day(prev)  # starea restaurată are deja un rând de jurnal în plus
    shutil.copy(prev / "audit.jsonl", state / "audit.jsonl")
    shutil.copy(prev / "paper.sqlite", state / "paper.sqlite")
    import sqlite3
    db = sqlite3.connect(state / "paper.sqlite")
    db.execute("DELETE FROM journal")
    db.commit(); db.close()
    audit_log.append(state / "audit.jsonl", "daily_run", {"equity": 10100.0}, NOW)
    problems = state_check.check(state, prev)
    assert any("s-a micșorat" in p for p in problems)


@pytest.mark.parametrize("name", ["paper.sqlite", "audit.jsonl", "last_run.json"])
def test_missing_file_is_rejected(days, name):
    prev, state = days
    run_day(state)
    (state / name).unlink()
    assert state_check.check(state, prev)


def test_new_account_needs_no_previous(tmp_path):
    state = tmp_path / "state"
    make_account(state)
    assert state_check.check(state, None, new_account=True) == []


def test_rejection_removes_stale_marker(days):
    prev, state = days
    run_day(state)
    assert state_check.main(["--state", str(state), "--previous", str(prev)]) == 0
    (state / "last_run.json").unlink()
    assert state_check.main(["--state", str(state), "--previous", str(prev)]) == 1
    assert not (state / "VALID.json").exists()


def verify(state):
    return subprocess.run(["bash", str(ROOT / "scripts/verify_marker.sh"), str(state)],
                          capture_output=True, text=True)


def test_publish_rejects_missing_marker_and_tampering(days):
    prev, state = days
    run_day(state)
    assert verify(state).returncode == 1               # fără marker
    assert state_check.main(["--state", str(state), "--previous", str(prev)]) == 0
    assert verify(state).returncode == 0
    with open(state / "paper.sqlite", "ab") as handle:  # modificat după punctul de control
        handle.write(b"x")
    assert verify(state).returncode == 1


def workflow():
    return (ROOT / ".github/workflows/cont-unic.yml").read_text()


def test_publish_runs_only_after_a_successful_step():
    text = workflow()
    publish = text.split("\n  publish:")[1]
    header = publish.split("steps:")[0]
    assert "needs.step.result == 'success'" in header
    assert "always()" not in header
    assert "verify_marker.sh" in publish
    assert publish.index("verify_marker.sh") < publish.index("git push")


def test_only_validated_state_is_uploaded_for_publish():
    text = workflow()
    step = text.split("\n  publish:")[0]
    assert step.index("src.bnd.state_check") < step.index("name: bnd-unic-${{ github.run_id }}")
    ok = step.split("name: bnd-unic-${{ github.run_id }}")[0].rsplit("- uses:", 1)[1]
    assert "if: success()" in ok and "always()" not in ok
    assert "bnd-unic-ESEC-" in step and "failure()" in step
    assert "cp state/paper.sqlite state/audit.jsonl prev/" in step
