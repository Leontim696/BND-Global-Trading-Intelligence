"""Restaurarea contului nu trebuie să creeze un cont nou peste cel real (audit #1, #2)."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


@pytest.fixture
def repos(tmp_path):
    bare, work = tmp_path / "remote.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(tmp_path, "clone", "-q", str(bare), str(work))
    return bare, work


def publish(work, branch, files):
    git(work, "checkout", "-q", "--orphan", branch)
    for name, text in files.items():
        (work / name).write_text(text)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "x")
    git(work, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    git(work, "checkout", "-q", "--orphan", "scratch")
    git(work, "rm", "-rfq", ".")


def run(script, work, *args, capital="", tmp=None):
    out = work / "gh_output"
    out.write_text("")
    env = {**os.environ, "CAPITAL": capital, "GITHUB_OUTPUT": str(out), "GITHUB_STEP_SUMMARY": str(work / "sum")}
    proc = subprocess.run(["bash", str(ROOT / "scripts" / script), *args], cwd=work, env=env,
                          capture_output=True, text=True)
    return proc, out.read_text()


def test_existing_account_is_restored(repos):
    _, work = repos
    publish(work, "cont", {"paper.sqlite": "DB", "audit.jsonl": "A"})
    proc, out = run("restore_account.sh", work, "cont", "nu exista", capital="10000")
    assert proc.returncode == 0 and "account=existing" in out
    assert (work / "state" / "paper.sqlite").read_text() == "DB" and (work / "state" / "audit.jsonl").read_text() == "A"


def test_missing_branch_with_capital_creates_new_without_capital_none(repos):
    _, work = repos
    assert "account=new" in run("restore_account.sh", work, "cont", "x", capital="10000")[1]
    proc, out = run("restore_account.sh", work, "cont", "nu exista", capital="")
    assert "account=none" in out and "nu exista" in (work / "sum").read_text()


def test_existing_branch_without_database_never_becomes_a_new_account(repos):
    _, work = repos
    publish(work, "cont", {"alt.txt": "x"})
    proc, out = run("restore_account.sh", work, "cont", "x", capital="10000")
    assert proc.returncode == 1 and "account=new" not in out and "paper.sqlite" in proc.stdout + proc.stderr


def test_unreachable_remote_never_becomes_a_new_account(repos):
    bare, work = repos
    publish(work, "cont", {"paper.sqlite": "DB"})
    git(work, "remote", "set-url", "origin", str(bare) + "-lipsa")
    proc, out = run("restore_account.sh", work, "cont", "x", capital="10000")
    assert proc.returncode == 1 and "account=" not in out


def test_missing_audit_is_a_warning_not_silent(repos):
    _, work = repos
    publish(work, "cont", {"paper.sqlite": "DB"})
    proc, out = run("restore_account.sh", work, "cont", "x")
    assert proc.returncode == 0 and "account=existing" in out and "audit.jsonl lipsește" in proc.stdout


def test_restore_branch_distinguishes_absent_from_failed(repos):
    bare, work = repos
    proc, _ = run("restore_branch.sh", work, "stare", "dest", "registry.sqlite")
    assert proc.returncode == 0 and "nu există încă" in proc.stdout
    publish(work, "stare", {"registry.sqlite": "R", "costs.sqlite": "C"})
    proc, _ = run("restore_branch.sh", work, "stare", "dest", "registry.sqlite", "costs.sqlite", "audit.jsonl")
    assert proc.returncode == 0 and (work / "dest" / "costs.sqlite").read_text() == "C"
    assert "audit.jsonl lipsește" in proc.stdout
    proc, _ = run("restore_branch.sh", work, "stare", "tot")
    assert (work / "tot" / "registry.sqlite").exists()
    git(work, "remote", "set-url", "origin", str(bare) + "-lipsa")
    assert run("restore_branch.sh", work, "stare", "d2", "registry.sqlite")[0].returncode == 1


def test_required_file_missing_on_existing_branch_stops_the_job(repos):
    _, work = repos
    publish(work, "stare", {"registry.sqlite": "R"})                  # costs.sqlite lipsește
    proc, _ = run("restore_branch.sh", work, "stare", "dest", "!registry.sqlite", "!costs.sqlite")
    assert proc.returncode == 1 and "obligatoriu" in proc.stdout + proc.stderr
    ok, _ = run("restore_branch.sh", work, "stare", "dest2", "!registry.sqlite", "audit.jsonl")
    assert ok.returncode == 0                                          # opțional lipsă = doar avertisment


def test_audit_required_for_the_unified_account(repos, monkeypatch):
    _, work = repos
    publish(work, "cont", {"paper.sqlite": "DB"})
    monkeypatch.setenv("REQUIRE_AUDIT", "1")
    proc, out = run("restore_account.sh", work, "cont", "x")
    assert proc.returncode == 1 and "GENESIS" in proc.stdout + proc.stderr and "account=existing" not in out


def test_a_token_is_not_added_when_the_checkout_already_kept_credentials(repos):
    _, work = repos
    publish(work, "stare", {"registry.sqlite": "R"})
    git(work, "config", "http.https://github.com/.extraheader", "AUTHORIZATION: basic eHg6eHg=")
    script = (ROOT / "scripts" / "restore_branch.sh").read_text()
    assert "extraheader" in script                                     # protecția împotriva antetelor duble există
    env = {**os.environ, "GH_TOKEN": "t"}
    proc = subprocess.run(["bash", str(ROOT / "scripts" / "restore_branch.sh"), "stare", "dest", "registry.sqlite"],
                          cwd=work, env=env, capture_output=True, text=True)
    assert proc.returncode == 0 and (work / "dest" / "registry.sqlite").read_text() == "R"
