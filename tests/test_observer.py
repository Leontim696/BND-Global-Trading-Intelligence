"""Modul observer-only (Proxmox, etapa A, issue #196): nu scrie în cont, nu rulează runnerul, o singură instanță."""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.bnd import audit_log, observer, paper_runner
from src.bnd.paper_engine import PaperEngine
from src.bnd.safety import SafetyError

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"
NOW = datetime(2026, 11, 2, 22, 25, tzinfo=timezone.utc)


@pytest.fixture
def mirror(tmp_path):
    folder = tmp_path / "mirror"
    folder.mkdir()
    PaperEngine.create(folder / "paper.sqlite", 11183.0, currency="USD", now=NOW).close()
    audit_log.append(folder / "audit.jsonl", "daily_run", {"equity": 11183.0, "orders": 3, "kill_switch": False}, NOW)
    return folder


@pytest.fixture
def observer_env(monkeypatch):
    monkeypatch.setenv("BND_OBSERVER_ONLY", "true")


def test_healthy_mirror_reports_ok_and_does_not_change_files(mirror, observer_env, tmp_path):
    before = {p.name: p.read_bytes() for p in mirror.iterdir() if p.is_file()}
    out = tmp_path / "public" / "status.json"
    assert observer.main(["--mirror", str(mirror), "--out", str(out), "--stale-hours", "100000"]) == 0
    status = json.loads(out.read_text())
    assert status["ok"] and status["verdict"] == "ok" and status["observer_only"] is True
    assert status["last_run"]["equity"] == 11183.0 and status["kill_switch"] is False
    assert "paper.sqlite" not in out.read_text()
    after = {p.name: p.read_bytes() for p in mirror.iterdir() if p.is_file() and p.name != ".observer.lock"}
    assert after == {k: v for k, v in before.items() if k != ".observer.lock"}


def test_refuses_without_observer_flag(mirror, tmp_path, monkeypatch):
    monkeypatch.delenv("BND_OBSERVER_ONLY", raising=False)
    assert observer.main(["--mirror", str(mirror), "--out", str(tmp_path / "s.json")]) == observer.EXIT["not_observer"]
    assert not (tmp_path / "s.json").exists()


def test_stale_mirror_and_corruption_are_reported(mirror, observer_env, tmp_path):
    status, verdict = observer.observe(mirror, now=NOW + timedelta(hours=40))
    assert verdict == "stale"
    (mirror / "paper.sqlite").write_bytes(b"gunoi" * 200)
    status, verdict = observer.observe(mirror, now=NOW)
    assert verdict == "integrity" and not status["ok"]


def test_tampered_audit_is_reported(mirror, observer_env):
    text = (mirror / "audit.jsonl").read_text().replace("11183.0", "99999.0")
    (mirror / "audit.jsonl").write_text(text)
    assert observer.observe(mirror, now=NOW)[1] == "integrity"


def test_missing_mirror_files(tmp_path, observer_env):
    empty = tmp_path / "gol"
    empty.mkdir()
    assert observer.observe(empty)[1] == "missing"
    assert observer.main(["--mirror", str(tmp_path / "nu-exista"), "--out", str(tmp_path / "s.json")]) == observer.EXIT["missing"]


def test_status_is_written_atomically(tmp_path):
    target = tmp_path / "p" / "status.json"
    observer.write_status(target, {"ok": True})
    observer.write_status(target, {"ok": False})
    assert json.loads(target.read_text()) == {"ok": False}
    assert not list(target.parent.glob("*.tmp"))


def test_second_instance_on_same_mirror_is_refused(mirror, tmp_path):
    env = {**os.environ, "BND_OBSERVER_ONLY": "true"}
    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import fcntl,sys,time; f=open(sys.argv[1]+'/.observer.lock','a+'); fcntl.flock(f, fcntl.LOCK_EX); print('x', flush=True); time.sleep(30)",
         str(mirror)], stdout=subprocess.PIPE, env=env)
    try:
        holder.stdout.readline()
        done = subprocess.run([sys.executable, "-m", "src.bnd.observer", "--mirror", str(mirror), "--out", str(tmp_path / "s.json")],
                              cwd=ROOT, env=env, capture_output=True, text=True)
        assert done.returncode == observer.EXIT["locked"], done.stdout + done.stderr
    finally:
        holder.kill()


# -- nicio cale de scriere în cont în modul observer ---------------------------------------------

def test_engine_and_runner_refuse_in_observer_mode(tmp_path, monkeypatch, mirror):
    monkeypatch.setenv("BND_OBSERVER_ONLY", "true")
    with pytest.raises(SafetyError):
        PaperEngine.open(mirror / "paper.sqlite")
    with pytest.raises(SafetyError):
        PaperEngine.create(tmp_path / "nou.sqlite", 1000.0, now=NOW)
    assert paper_runner.main(["--state", str(mirror / "paper.sqlite"), "--data-dir", str(tmp_path)]) == 2
    # runnerul nu a creat/modificat nimic
    db = sqlite3.connect(f"file:{mirror / 'paper.sqlite'}?mode=ro", uri=True)
    assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
    db.close()


def test_runner_exits_with_error_not_a_trade_in_observer_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("BND_OBSERVER_ONLY", "true")
    assert paper_runner.main(["--state", str(tmp_path / "s.sqlite"), "--data-dir", str(tmp_path), "--capital", "1000"]) == 2
    assert not (tmp_path / "s.sqlite").exists()


def test_observer_module_has_no_trading_or_write_imports():
    source = (ROOT / "src/bnd/observer.py").read_text()
    for forbidden in ("paper_engine", "paper_runner", "PaperEngine", "urllib", "requests", "socket", "subprocess"):
        assert forbidden not in source
    assert "mode=ro" in source


# -- fișierele de deploy ----------------------------------------------------------------------------

def test_deploy_units_are_observer_only_and_never_enable_the_trading_timer():
    observer_dir = DEPLOY / "observer"
    for path in observer_dir.iterdir():
        text = path.read_text()
        assert "paper_runner" not in text, path.name
        if path.name != "install.sh":
            assert "enable" not in text.replace("EnvironmentFile", "") or path.suffix not in (".sh",), path.name
    install = (observer_dir / "install.sh").read_text()
    assert "enable --now bnd-observer.timer" in install
    assert "enable --now bnd-paper" not in install and "start bnd-paper" not in install
    assert "bnd-paper.timer e activ" in install                      # refuză lângă runner
    service = (observer_dir / "bnd-observer.service").read_text()
    assert "BND_OBSERVER_ONLY" in (observer_dir / "env.example").read_text()
    assert "Conflicts=bnd-paper.service bnd-paper.timer" in service and "NoNewPrivileges=true" in service
    assert "User=bnd-observer" in service and "ProtectSystem=strict" in service


def test_observer_dockerfile_is_unprivileged_observer_only():
    text = (DEPLOY / "Dockerfile.observer").read_text()
    assert "BND_OBSERVER_ONLY=true" in text and "USER bnd" in text and "paper_runner" not in text
    assert "HEALTHCHECK" in text
    runner = (DEPLOY / "Dockerfile.runner").read_text()
    assert "ETAPA C" in runner and "USER bnd" in runner and not (DEPLOY / "Dockerfile").exists()


def test_old_runner_timer_is_not_referenced_for_activation_anywhere_in_observer_docs():
    docs = (ROOT / "docs/PROXMOX.md").read_text()
    assert "systemctl enable --now bnd-paper.timer" not in docs.split("Etapa C")[0]
    assert "#196" in docs


# -- sincronizarea (script bash) cu un remote local -------------------------------------------------

def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


@pytest.fixture
def remote(tmp_path, mirror):
    bare, work = tmp_path / "remote.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(tmp_path, "clone", "-q", str(bare), str(work))
    git(work, "checkout", "-q", "--orphan", "cont-unic")
    shutil.copy(mirror / "paper.sqlite", work)
    shutil.copy(mirror / "audit.jsonl", work)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "x")
    git(work, "push", "-q", "origin", "HEAD:refs/heads/cont-unic")
    return bare, work


def sync(tmp_path, bare, **extra):
    env = {**os.environ, "BND_DATA_DIR": str(tmp_path / "data"), "BND_REMOTE": str(bare), "BND_RETRY_SLEEP": "0", **extra}
    return subprocess.run(["bash", str(DEPLOY / "observer/sync.sh")], cwd=ROOT, env=env, capture_output=True, text=True)


def test_sync_mirrors_a_valid_account_and_keeps_previous_for_rollback(tmp_path, remote):
    bare, work = remote
    first = sync(tmp_path, bare)
    assert first.returncode == 0, first.stdout + first.stderr
    data = tmp_path / "data"
    assert (data / "mirror/paper.sqlite").is_file() and (data / "mirror/COMMIT").is_file()
    audit_log.append(work / "audit.jsonl", "daily_run", {"equity": 11200.0, "orders": 0, "kill_switch": False}, NOW)
    git(work, "commit", "-qam", "y")
    git(work, "push", "-q", "origin", "HEAD:refs/heads/cont-unic")
    second = sync(tmp_path, bare)
    assert second.returncode == 0, second.stdout + second.stderr
    assert (data / "mirror.prev/audit.jsonl").is_file()
    assert (data / "mirror/audit.jsonl").read_text() != (data / "mirror.prev/audit.jsonl").read_text()


def test_sync_keeps_old_mirror_when_new_one_is_corrupt_or_remote_is_down(tmp_path, remote):
    bare, work = remote
    assert sync(tmp_path, bare).returncode == 0
    data = tmp_path / "data"
    good = (data / "mirror/paper.sqlite").read_bytes()
    (work / "paper.sqlite").write_bytes(b"stricat" * 50)
    git(work, "commit", "-qam", "bad")
    git(work, "push", "-q", "origin", "HEAD:refs/heads/cont-unic")
    bad = sync(tmp_path, bare)
    assert bad.returncode == 1 and (data / "mirror/paper.sqlite").read_bytes() == good
    down = sync(tmp_path, tmp_path / "nu-exista.git")
    assert down.returncode == 1 and (data / "mirror/paper.sqlite").read_bytes() == good


def test_sync_never_pushes():
    assert "push" not in (DEPLOY / "observer/sync.sh").read_text().replace("# ", "").split("set -euo")[1]


def test_backup_restore_check_script(tmp_path, mirror):
    backups = tmp_path / "bk"
    backups.mkdir()
    shutil.copy(mirror / "paper.sqlite", backups / "paper_20261102_222500.sqlite")
    shutil.copy(mirror / "audit.jsonl", backups / "audit_20261102_222500.jsonl")
    env = {**os.environ, "BND_BACKUP_DIR": str(backups)}
    ok = subprocess.run(["bash", str(DEPLOY / "observer/verify-backup.sh")], cwd=ROOT, env=env, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    (backups / "paper_20261102_222500.sqlite").write_bytes(b"x" * 100)
    bad = subprocess.run(["bash", str(DEPLOY / "observer/verify-backup.sh")], cwd=ROOT, env=env, capture_output=True, text=True)
    assert bad.returncode != 0


def test_install_script_refuses_next_to_active_runner_timer(tmp_path):
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "systemctl").write_text('#!/bin/sh\n[ "$1" = "is-enabled" ] && exit 0\nexit 1\n')
    (fake / "systemctl").chmod(0o755)
    done = subprocess.run(["bash", str(DEPLOY / "observer/install.sh"), "--dry-run"], cwd=ROOT, capture_output=True, text=True,
                          env={**os.environ, "PATH": f"{fake}:{os.environ['PATH']}"})
    assert done.returncode == 1 and "bnd-paper.timer e activ" in done.stderr


def test_install_dry_run_changes_nothing(tmp_path):
    done = subprocess.run(["bash", str(DEPLOY / "observer/install.sh"), "--dry-run"], cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "[dry-run]" in done.stdout
