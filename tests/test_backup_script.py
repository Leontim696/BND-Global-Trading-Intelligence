"""deploy/backup.sh: copie consistentă și verificată, fără pachetul sqlite3, cu rotație care nu pierde copii bune."""
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.bnd import audit_log
from src.bnd.paper_engine import PaperEngine

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "backup.sh"
NOW = datetime(2026, 11, 2, 22, 25, tzinfo=timezone.utc)


@pytest.fixture
def state(tmp_path):
    folder = tmp_path / "state"
    folder.mkdir()
    PaperEngine.create(folder / "paper.sqlite", 5000.0, currency="USD", now=NOW).close()
    audit_log.append(folder / "audit.jsonl", "daily_run", {"equity": 5000.0}, NOW)
    return folder


def run(state, dest, **extra):
    env = {**os.environ, "BND_STATE_DIR": str(state), "BND_BACKUP_DIR": str(dest), **extra}
    return subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env)


def test_backup_makes_a_valid_copy_and_an_audit_copy_without_the_sqlite3_cli(tmp_path, state):
    # PATH fără binarul `sqlite3`: scriptul nu mai depinde de el
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("bash", "python3", "date", "mkdir", "mv", "cp", "rm", "ls", "tail", "xargs", "dirname", "env"):
        found = shutil.which(name)
        if found:
            (bin_dir / name).symlink_to(found)
    dest = tmp_path / "bk"
    done = run(state, dest, PATH=str(bin_dir))
    assert done.returncode == 0, done.stdout + done.stderr
    copies = sorted(dest.glob("paper_*.sqlite"))
    assert len(copies) == 1 and len(list(dest.glob("audit_*.jsonl"))) == 1
    db = sqlite3.connect(copies[0])
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert db.execute("SELECT initial_capital FROM account").fetchone()[0] == 5000.0
    db.close()
    assert not list(dest.glob(".paper_*.tmp"))                    # fără resturi temporare


def test_a_failing_backup_leaves_no_partial_file_and_does_not_evict_good_copies(tmp_path, state):
    dest = tmp_path / "bk"
    assert run(state, dest, BND_BACKUP_KEEP="1").returncode == 0
    good = sorted(dest.glob("paper_*.sqlite"))
    assert len(good) == 1
    (state / "paper.sqlite").write_bytes(b"gunoi" * 100)           # contul sursă e stricat
    bad = run(state, dest, BND_BACKUP_KEEP="1")
    assert bad.returncode != 0
    assert sorted(dest.glob("paper_*.sqlite")) == good               # copia bună a rămas
    assert not list(dest.glob(".paper_*.tmp")) and not list(dest.glob("paper_*.sqlite-journal"))


def test_rotation_keeps_only_the_newest_copies(tmp_path, state):
    dest = tmp_path / "bk"
    dest.mkdir()
    for i in range(5):
        old = dest / f"paper_2026010{i}_000000.sqlite"
        old.write_bytes(b"x")
        os.utime(old, (1000 + i, 1000 + i))
    assert run(state, dest, BND_BACKUP_KEEP="3").returncode == 0
    assert len(list(dest.glob("paper_*.sqlite"))) == 3


def test_backup_script_does_not_use_the_sqlite3_binary():
    text = SCRIPT.read_text()
    assert "\nsqlite3 " not in text and "integrity_check" in text
