"""Observer: sănătatea datelor ≠ sănătatea sincronizării; token fără urme; HTTP doar pe loopback (feedback 01.11)."""
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.bnd import audit_log, observer
from src.bnd.paper_engine import PaperEngine

ROOT = Path(__file__).resolve().parents[1]
OBS = ROOT / "deploy" / "observer"
TOKEN = "github_pat_11ABCDEFG0abcdefghijkl_ZZZZsecretsecretsecret"


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def head(bare):
    return subprocess.run(["git", "rev-parse", "refs/heads/cont-unic"], cwd=bare, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def remote(tmp_path):
    now = datetime.now(timezone.utc)
    bare, work = tmp_path / "remote.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(tmp_path, "clone", "-q", str(bare), str(work))
    git(work, "checkout", "-q", "--orphan", "cont-unic")
    PaperEngine.create(work / "paper.sqlite", 11183.0, currency="USD", now=now).close()
    audit_log.append(work / "audit.jsonl", "daily_run", {"equity": 11183.0, "orders": 1, "kill_switch": False}, now)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "x")
    git(work, "push", "-q", "origin", "HEAD:refs/heads/cont-unic")
    return bare, work


def env_for(tmp_path, bare, **extra):
    return {**os.environ, "BND_DATA_DIR": str(tmp_path / "data"), "BND_REMOTE": str(bare), "BND_RETRY_SLEEP": "0",
            "PYTHONPATH": str(ROOT), **extra}


def run_once(tmp_path, bare, **extra):
    return subprocess.run(["bash", str(OBS / "run-once.sh")], cwd=ROOT, env=env_for(tmp_path, bare, **extra),
                          capture_output=True, text=True)


def status(tmp_path):
    return json.loads((tmp_path / "data/public/status.json").read_text())


def sync_state(tmp_path):
    return json.loads((tmp_path / "data/sync.json").read_text())


def test_successful_sync_reports_commit_time_and_ok(tmp_path, remote):
    bare, _ = remote
    assert run_once(tmp_path, bare).returncode == 0
    s, sync = status(tmp_path), sync_state(tmp_path)
    assert s["sync_ok"] is True and s["data_ok"] is True and s["ok"] is True and s["verdict"] == "ok"
    assert s["mirror_commit"] == head(bare) and s["last_successful_sync"] and sync["consecutive_failures"] == 0
    assert subprocess.run(["bash", str(OBS / "healthcheck.sh")], env=env_for(tmp_path, bare), capture_output=True).returncode == 0


def test_unavailable_remote_is_not_reported_as_a_successful_sync(tmp_path, remote):
    bare, _ = remote
    assert run_once(tmp_path, bare).returncode == 0
    good_commit, good_time = status(tmp_path)["mirror_commit"], status(tmp_path)["last_successful_sync"]
    down = run_once(tmp_path, tmp_path / "nu-exista.git")
    s, sync = status(tmp_path), sync_state(tmp_path)
    assert "Sincronizarea a eșuat" in down.stdout
    assert sync["sync_ok"] is False and sync["sync_error"] == "remote_indisponibil" and sync["consecutive_failures"] == 1
    assert s["sync_ok"] is False and s["ok"] is False and s["verdict"] == "sync_failed"
    assert s["data_ok"] is True                                  # datele din oglindă rămân valide, dar nu sunt „proaspete”
    assert s["mirror_commit"] == good_commit and s["last_successful_sync"] == good_time    # ultima reușită se păstrează
    again = run_once(tmp_path, tmp_path / "nu-exista.git")
    assert sync_state(tmp_path)["consecutive_failures"] == 2 and again.returncode == observer.EXIT["sync_failed"]
    health = subprocess.run(["bash", str(OBS / "healthcheck.sh")], env=env_for(tmp_path, bare), capture_output=True, text=True)
    assert health.returncode != 0 and "sincronizarea" in (health.stdout + health.stderr)


def test_recovery_resets_the_failure_counter(tmp_path, remote):
    bare, _ = remote
    first = run_once(tmp_path, tmp_path / "nu-exista.git")
    assert first.returncode == observer.EXIT["missing"]
    assert status(tmp_path)["verdict"] == "missing" and status(tmp_path)["sync_ok"] is False and status(tmp_path)["ok"] is False
    assert run_once(tmp_path, bare).returncode == 0
    assert sync_state(tmp_path)["consecutive_failures"] == 0 and status(tmp_path)["ok"] is True


def test_corrupt_remote_data_fails_the_sync_but_keeps_the_valid_mirror(tmp_path, remote):
    bare, work = remote
    run_once(tmp_path, bare)
    good = (tmp_path / "data/mirror/paper.sqlite").read_bytes()
    (work / "paper.sqlite").write_bytes(b"stricat" * 50)
    git(work, "commit", "-qam", "bad")
    git(work, "push", "-q", "origin", "HEAD:refs/heads/cont-unic")
    run_once(tmp_path, bare)
    assert (tmp_path / "data/mirror/paper.sqlite").read_bytes() == good
    s = status(tmp_path)
    assert s["sync_ok"] is False and s["data_ok"] is True and s["verdict"] == "sync_failed"
    assert sync_state(tmp_path)["sync_error"] == "oglinda_noua_invalida"


def test_missing_file_on_remote_is_recorded_with_its_reason(tmp_path, remote):
    bare, work = remote
    git(work, "rm", "-q", "audit.jsonl")
    git(work, "commit", "-qm", "fara audit")
    git(work, "push", "-q", "origin", "HEAD:refs/heads/cont-unic")
    run_once(tmp_path, bare)
    assert sync_state(tmp_path)["sync_error"] == "lipseste_audit.jsonl" and sync_state(tmp_path)["sync_ok"] is False


def test_unreadable_token_file_fails_loudly_instead_of_silently_going_unauthenticated(tmp_path, remote):
    bare, _ = remote
    done = run_once(tmp_path, bare, BND_TOKEN_FILE=str(tmp_path / "nu-exista"))
    assert "nu poate fi citit" in done.stdout
    assert sync_state(tmp_path)["sync_error"] == "token_ilizibil" and sync_state(tmp_path)["sync_ok"] is False


def test_a_concurrent_sync_is_not_recorded_as_a_failure(tmp_path, remote):
    bare, _ = remote
    data = tmp_path / "data"
    data.mkdir()
    holder = subprocess.Popen(["bash", "-c", f"exec 9>{data}/.sync.lock; flock 9; echo x; sleep 20"], stdout=subprocess.PIPE)
    try:
        holder.stdout.readline()
        done = subprocess.run(["bash", str(OBS / "sync.sh")], cwd=ROOT, env=env_for(tmp_path, bare), capture_output=True, text=True)
        assert done.returncode == 4 and not (data / "sync.json").exists()
    finally:
        holder.kill()


def test_stale_successful_sync_turns_the_status_red_even_if_the_last_attempt_was_ok():
    now = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
    info = observer._sync_info
    data = Path(__file__).parent
    assert info(data / "nu-exista.json", now)["sync_ok"] is False


def test_record_sync_counts_failures_and_keeps_last_success(tmp_path):
    t0 = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    observer.record_sync(tmp_path, True, now=t0)
    (tmp_path / "mirror").mkdir()
    (tmp_path / "mirror" / "COMMIT").write_text("abc123\n")
    observer.record_sync(tmp_path, True, now=t0)
    state = observer.record_sync(tmp_path, False, "remote_indisponibil", now=t0 + timedelta(hours=1))
    assert state["last_successful_sync"] == t0.isoformat(timespec="seconds") and state["mirror_commit"] == "abc123"
    assert state["consecutive_failures"] == 1
    assert observer.record_sync(tmp_path, False, "x", now=t0 + timedelta(hours=2))["consecutive_failures"] == 2


def test_observe_distinguishes_old_sync_from_failed_sync(tmp_path):
    now = datetime.now(timezone.utc)
    mirror = tmp_path / "m"
    mirror.mkdir()
    PaperEngine.create(mirror / "paper.sqlite", 1000.0, currency="USD", now=now).close()
    audit_log.append(mirror / "audit.jsonl", "daily_run", {"equity": 1000.0, "orders": 0, "kill_switch": False}, now)
    observer.record_sync(tmp_path, True, now=now - timedelta(hours=5))
    status_, verdict = observer.observe(mirror, now=now, sync_file=tmp_path / "sync.json")
    assert verdict == "sync_failed" and status_["data_ok"] and not status_["ok"] and "veche" in status_["sync_error"]
    observer.record_sync(tmp_path, True, now=now - timedelta(minutes=10))
    assert observer.observe(mirror, now=now, sync_file=tmp_path / "sync.json")[1] == "ok"


# -- token: fără urme în argumente, URL, istoric ----------------------------------------------------

def test_token_never_appears_in_git_arguments_or_environment(tmp_path):
    log, envlog = tmp_path / "args.log", tmp_path / "env.log"
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "git").write_text(f'#!/bin/sh\necho "$@" >> {log}\nenv >> {envlog}\nexit 0\n')
    (fake / "git").chmod(0o755)
    tokfile = tmp_path / "tok"
    tokfile.write_text(TOKEN + "\n")
    env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "BND_TOKEN_FILE": str(tokfile)}
    subprocess.run(["bash", "-c", f"source {OBS}/gitauth.sh; git_net ls-remote https://github.com/x/y.git refs/heads/cont-unic"],
                   env=env, check=True)
    import base64
    args, envs = log.read_text(), envlog.read_text()
    encoded = base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode()
    for secret in (TOKEN, encoded):
        assert secret not in args and secret not in envs                # nici în argumente, nici în mediul lui git
    assert f"GIT_ASKPASS={OBS}/askpass.sh" in envs and "GIT_TERMINAL_PROMPT=0" in envs
    assert "GIT_CONFIG_KEY_0=credential.helper" in envs and "GIT_CONFIG_VALUE_0=\n" in envs + "\n"
    assert "https://github.com/x/y.git" in args and "@" not in args


def test_sources_never_put_a_token_in_urls_or_arguments():
    for script in OBS.glob("*.sh"):
        text = script.read_text()
        assert "x-access-token:${" not in text.replace("printf 'x-access-token:%s'", ""), script.name
        assert "http.extraheader=AUTHORIZATION" not in text, script.name       # forma veche, vizibilă în ps (git -c ...)
        assert 'GIT_CONFIG_VALUE_0="AUTHORIZATION' not in text, script.name    # forma din #227: token în mediul lui git
        assert "https://x-access-token" not in text and "ghp_${" not in text, script.name


def test_set_token_writes_a_private_file_from_stdin(tmp_path):
    dest = tmp_path / "etc" / "token"
    done = subprocess.run(["bash", str(OBS / "set-token.sh")], input=TOKEN + "\n", text=True, capture_output=True,
                          env={**os.environ, "BND_TOKEN_FILE": str(dest)})
    assert done.returncode == 0, done.stderr
    assert dest.read_text().strip() == TOKEN and (dest.stat().st_mode & 0o007) == 0
    assert TOKEN not in done.stdout + done.stderr
    empty = subprocess.run(["bash", str(OBS / "set-token.sh")], input="\n", text=True, capture_output=True,
                           env={**os.environ, "BND_TOKEN_FILE": str(tmp_path / "t2")})
    assert empty.returncode == 1 and not (tmp_path / "t2").exists()


def check(tmp_path, bare, tokfile, home=None):
    return subprocess.run(["bash", str(OBS / "check-token.sh")], capture_output=True, text=True,
                          env={**os.environ, "BND_TOKEN_FILE": str(tokfile), "BND_REMOTE": str(bare),
                               "HOME": str(home or tmp_path / "home")})


def test_check_token_verifies_permissions_remote_read_and_history(tmp_path, remote):
    bare, _ = remote
    tokfile = tmp_path / "tok"
    tokfile.write_text(TOKEN + "\n")
    tokfile.chmod(0o600)
    good = check(tmp_path, bare, tokfile)
    assert good.returncode == 0, good.stdout + good.stderr
    assert "citirea ramurii cont-unic funcționează" in good.stdout and TOKEN not in good.stdout + good.stderr
    tokfile.chmod(0o644)                                          # citibil de toți
    loose = check(tmp_path, bare, tokfile)
    assert loose.returncode == 1 and "citibil de 'alții'" in loose.stdout
    tokfile.chmod(0o600)
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bash_history").write_text(f"git clone https://x-access-token:{TOKEN}@github.com/a/b\n")
    leaked = check(tmp_path, bare, tokfile, home)
    assert leaked.returncode == 1 and "REVOCĂ" in leaked.stdout and TOKEN not in leaked.stdout
    assert check(tmp_path, tmp_path / "nu-exista.git", tokfile).returncode == 1       # fără acces de citire real


def test_check_token_flags_classic_tokens(tmp_path, remote):
    bare, _ = remote
    tokfile = tmp_path / "tok"
    tokfile.write_text("ghp_" + "a" * 36 + "\n")
    tokfile.chmod(0o600)
    done = check(tmp_path, bare, tokfile)
    assert done.returncode == 1 and "token clasic" in done.stdout


def test_bootstrap_clones_without_credentials_in_the_remote(tmp_path, remote):
    bare, _ = remote
    tokfile = tmp_path / "tok"
    tokfile.write_text(TOKEN + "\n")
    dest = tmp_path / "clone"
    done = subprocess.run(["bash", str(OBS / "bootstrap.sh"), str(dest)], capture_output=True, text=True,
                          env={**os.environ, "BND_TOKEN_FILE": str(tokfile), "BND_REMOTE": str(bare)})
    assert done.returncode == 0, done.stderr
    config = (dest / ".git" / "config").read_text()
    assert TOKEN not in config and "extraheader" not in config and "x-access-token" not in config
    assert subprocess.run(["bash", str(OBS / "bootstrap.sh"), str(dest)], capture_output=True, env=os.environ).returncode == 1


# -- HTTP: instalat dar nepornit; doar loopback ----------------------------------------------------

def bind_check(bind, **extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("BND_HTTP")}
    return subprocess.run(["bash", str(OBS / "http-bind-check.sh")], capture_output=True, text=True,
                          env={**env, "BND_HTTP_BIND": bind, **extra})


@pytest.mark.parametrize("bind", ["127.0.0.1", "::1", "localhost"])
def test_loopback_is_accepted(bind):
    assert bind_check(bind).returncode == 0


@pytest.mark.parametrize("bind", ["0.0.0.0", "::", ""])
def test_all_interfaces_are_always_refused(bind):
    assert bind_check(bind).returncode == 1
    assert bind_check(bind, BND_HTTP_ALLOW_NON_LOOPBACK="yes").returncode == 1


def test_other_addresses_need_explicit_confirmation():
    assert bind_check("10.8.0.2").returncode == 1
    assert bind_check("10.8.0.2", BND_HTTP_ALLOW_NON_LOOPBACK="yes").returncode == 0


def test_http_service_uses_the_checked_bind_and_is_not_started_by_default():
    unit = (OBS / "bnd-observer-http.service").read_text()
    assert "ExecStartPre=" in unit and "http-bind-check.sh" in unit and "--bind ${BND_HTTP_BIND}" in unit
    assert "127.0.0.1" not in unit.split("ExecStart=")[1].split("\n")[0]
    assert "BND_HTTP_BIND=127.0.0.1" in (OBS / "env.example").read_text()
    plain = subprocess.run(["bash", str(OBS / "install.sh"), "--dry-run"], cwd=ROOT, capture_output=True, text=True)
    assert plain.returncode == 0, plain.stderr
    assert "bnd-observer-http.service" in plain.stdout and "enable --now bnd-observer-http" not in plain.stdout
    assert "NU pornit" in plain.stdout
    with_http = subprocess.run(["bash", str(OBS / "install.sh"), "--dry-run", "--with-http"], cwd=ROOT, capture_output=True, text=True)
    assert "enable --now bnd-observer-http.service" in with_http.stdout
    assert subprocess.run(["bash", str(OBS / "install.sh"), "--oops"], cwd=ROOT, capture_output=True).returncode == 2


def test_install_sets_group_readable_config_for_the_service_user():
    plain = subprocess.run(["bash", str(OBS / "install.sh"), "--dry-run"], cwd=ROOT, capture_output=True, text=True).stdout
    assert "-o root -g bnd-observer /etc/bnd-observer" in plain and "0640 -o root -g bnd-observer" in plain.replace("-m 0640", "0640")


def test_docs_cover_private_repo_bootstrap_token_permissions_and_home_assistant_access():
    docs = (ROOT / "docs/PROXMOX.md").read_text()
    for needle in ("set-token.sh", "check-token.sh", "bootstrap.sh", "root:bnd-observer", "history", "--with-http",
                   "BND_HTTP_BIND", "sync_ok", "last_successful_sync", "mirror_commit", "WireGuard", "nginx"):
        assert needle in docs, needle
