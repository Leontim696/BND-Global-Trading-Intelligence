"""Persistență și recuperare: oprire bruscă, rulări simultane, jurnal rupt, fără duplicate."""

import json
import os
import signal
import subprocess
import sys
import textwrap
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from src.bnd import audit_log
from src.bnd.paper_engine import PaperEngine
from src.bnd.reconcile import reconcile

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 31, tzinfo=timezone.utc)


def _append(args):
    path, number = args
    audit_log.append(path, "test", {"n": number}, NOW)


def test_concurrent_appends_keep_one_valid_chain(tmp_path):
    path = tmp_path / "audit.jsonl"
    with ProcessPoolExecutor(max_workers=4) as pool:
        list(pool.map(_append, [(str(path), n) for n in range(40)]))

    ok, message = audit_log.verify(path)
    assert ok, message
    assert len(path.read_text().splitlines()) == 40


def test_a_torn_last_line_does_not_stop_the_log_and_stays_visible(tmp_path):
    path = tmp_path / "audit.jsonl"
    audit_log.append(path, "a", {}, NOW)
    audit_log.append(path, "b", {}, NOW)
    with path.open("a") as handle:
        handle.write('{"time": "2026-10-31T00:00:00+00:00", "kind": "c", "da')   # oprire în mijlocul scrierii

    audit_log.append(path, "d", {}, NOW)           # nu aruncă excepție

    ok, message = audit_log.verify(path)
    assert not ok and "Rândul 3" in message         # stricăciunea rămâne vizibilă
    last = json.loads(path.read_text().splitlines()[-1])
    assert last["kind"] == "d"


def test_tampering_with_a_past_row_is_detected(tmp_path):
    path = tmp_path / "audit.jsonl"
    for kind in "abc":
        audit_log.append(path, kind, {"v": 1}, NOW)
    path.write_text(path.read_text().replace('"v": 1', '"v": 2', 1))

    assert not audit_log.verify(path)[0]


def test_killed_process_in_the_middle_of_a_write_leaves_the_account_consistent(tmp_path):
    state = tmp_path / "paper.sqlite"
    PaperEngine.create(state, 10_000.0, currency="USD", now=NOW).close()
    child = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(ROOT)!r})
        from src.bnd.paper_engine import PaperEngine
        engine = PaperEngine.open({str(state)!r})
        engine._db.execute("BEGIN IMMEDIATE")
        engine._db.execute("UPDATE account SET cash = cash - 5000")
        print("ready", flush=True)
        time.sleep(60)
    """)
    process = subprocess.Popen([sys.executable, "-I", "-c", child], stdout=subprocess.PIPE,
                               env={**os.environ, "PYTHONPATH": str(ROOT)})
    assert process.stdout.readline().strip() == b"ready"
    os.kill(process.pid, signal.SIGKILL)
    process.wait()

    engine = PaperEngine.open(state)
    try:
        assert engine.account()["cash"] == 10_000.0     # scrierea neterminată nu a rămas
        assert reconcile(engine)["ok"]
    finally:
        engine.close()


def test_account_file_copy_after_close_opens_with_no_leftover_journal(tmp_path):
    state = tmp_path / "paper.sqlite"
    engine = PaperEngine.create(state, 5_000.0, currency="USD", now=NOW)
    engine.record("daily_run", {"time": NOW.isoformat(), "equity": 5_000.0}, NOW)
    engine.close()

    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["paper.sqlite"]                    # workflow-ul publică un singur fișier
    copy = tmp_path / "copy.sqlite"
    copy.write_bytes(state.read_bytes())
    assert PaperEngine.open(copy).account()["initial_capital"] == 5_000.0
