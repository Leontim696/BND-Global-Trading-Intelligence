"""Observer: token prin GIT_ASKPASS (fără mediu/argumente/fișiere) și sincronizare întreruptă brusc (verificarea 3)."""
import base64
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from src.bnd import audit_log, observer
from src.bnd.paper_engine import PaperEngine

ROOT = Path(__file__).resolve().parents[1]
OBS = ROOT / "deploy" / "observer"
TOKEN = "github_pat_11ZZZZZZZ0qwertyuiop_SECRETSECRETSECRETSECRET"
ENCODED = base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode()
HTTP_BACKEND = Path(subprocess.run(["git", "--exec-path"], capture_output=True, text=True).stdout.strip()) / "git-http-backend"
LINUX = Path("/proc/self/environ").exists()


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def head(bare):
    return subprocess.run(["git", "rev-parse", "refs/heads/cont-unic"], cwd=bare, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def remote(tmp_path):
    now = datetime.now(timezone.utc)
    bare, work = tmp_path / "srv" / "remote.git", tmp_path / "work"
    bare.parent.mkdir()
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(tmp_path, "clone", "-q", str(bare), str(work))
    git(work, "checkout", "-q", "--orphan", "cont-unic")
    PaperEngine.create(work / "paper.sqlite", 11183.0, currency="USD", now=now).close()
    audit_log.append(work / "audit.jsonl", "daily_run", {"equity": 11183.0, "orders": 1, "kill_switch": False}, now)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "x")
    git(work, "push", "-q", "origin", "HEAD:refs/heads/cont-unic")
    return bare, work


def push_new_day(work, equity):
    audit_log.append(work / "audit.jsonl", "daily_run", {"equity": equity, "orders": 0, "kill_switch": False},
                     datetime.now(timezone.utc))
    git(work, "commit", "-qam", f"zi {equity}")
    git(work, "push", "-q", "origin", "HEAD:refs/heads/cont-unic")


class GitServer:
    """Server HTTP real care cere Basic auth și apoi servește repo-ul prin `git http-backend`."""

    def __init__(self, root, token, delay=0.0):
        outer = self
        self.seen, self.delay, self.token = [], delay, token

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_any(self):
                auth = self.headers.get("Authorization")
                outer.seen.append(auth)
                expected = "Basic " + base64.b64encode(f"x-access-token:{outer.token}".encode()).decode()
                if auth != expected:
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", 'Basic realm="bnd"')
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if outer.delay:
                    time.sleep(outer.delay)
                path, _, query = self.path.partition("?")
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                env = {"GIT_PROJECT_ROOT": str(root), "GIT_HTTP_EXPORT_ALL": "1", "REQUEST_METHOD": self.command,
                       "PATH_INFO": path, "QUERY_STRING": query, "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                       "CONTENT_LENGTH": str(length), "REMOTE_USER": "x-access-token", "PATH": os.environ["PATH"]}
                if self.headers.get("Content-Encoding"):
                    env["HTTP_CONTENT_ENCODING"] = self.headers["Content-Encoding"]
                if self.headers.get("Git-Protocol"):
                    env["HTTP_GIT_PROTOCOL"] = self.headers["Git-Protocol"]
                out = subprocess.run([str(HTTP_BACKEND)], input=body, capture_output=True, env=env).stdout
                head_raw, _, payload = out.partition(b"\r\n\r\n")
                status, headers = 200, []
                for line in head_raw.decode().split("\r\n"):
                    key, _, value = line.partition(": ")
                    if key.lower() == "status":
                        status = int(value.split()[0])
                    elif key:
                        headers.append((key, value))
                self.send_response(status)
                for key, value in headers:
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = handle_any

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/remote.git"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server(remote):
    servers = []

    def make(delay=0.0, token=TOKEN):
        s = GitServer(remote[0].parent, token, delay)
        servers.append(s)
        return s
    yield make
    for s in servers:
        s.close()


def env_for(tmp_path, remote_url, **extra):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {**os.environ, "BND_DATA_DIR": str(tmp_path / "data"), "BND_REMOTE": str(remote_url), "BND_RETRY_SLEEP": "0",
            "PYTHONPATH": str(ROOT), "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"), **extra}


def scan_processes(secrets):
    """Caută secretele în mediul și argumentele tuturor proceselor vizibile; întoarce ce a găsit."""
    found = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) == os.getpid():
            continue
        for name in ("environ", "cmdline"):
            try:
                blob = Path(f"/proc/{pid}/{name}").read_bytes()
            except OSError:
                continue
            for secret in secrets:
                if secret.encode() in blob:
                    found.append((pid, name, secret[:12]))
    return found


needs_backend = pytest.mark.skipif(not HTTP_BACKEND.exists(), reason="git-http-backend indisponibil")
needs_proc = pytest.mark.skipif(not LINUX, reason="necesită /proc")


# ===================================================================== 1. AUTENTIFICARE =====================

@needs_proc
def test_control_the_old_env_approach_was_visible_in_proc():
    """Control: scanerul chiar găsește un secret pus în mediu (varianta din #227: GIT_CONFIG_VALUE_0)."""
    proc = subprocess.Popen(["sleep", "5"], env={**os.environ, "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {ENCODED}"})
    try:
        assert scan_processes([ENCODED])
    finally:
        proc.kill()


@needs_backend
@needs_proc
def test_token_reaches_the_server_but_never_the_environment_or_arguments_of_git(tmp_path, remote, server):
    srv = server(delay=1.2)                                  # răspuns lent: avem timp să scanăm procesele
    proc = subprocess.Popen(["bash", str(OBS / "sync.sh")], cwd=ROOT, env=env_for(tmp_path, srv.url, BND_TOKEN_FILE=str(_tok(tmp_path))),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    hits = []
    while proc.poll() is None:
        hits += scan_processes([TOKEN, ENCODED])
        time.sleep(0.03)
    output = proc.stdout.read()
    assert proc.returncode == 0, output
    assert hits == [], f"token găsit în procese: {hits}"
    assert srv.seen[0] is None                                # întâi cerere fără autentificare (401)...
    assert f"Basic {ENCODED}" in srv.seen                     # ...apoi token doar în antetul trimis serverului
    state = json.loads((tmp_path / "data/sync.json").read_text())
    assert state["sync_ok"] is True and state["mirror_commit"] == head(remote[0])
    assert TOKEN not in output and ENCODED not in output


def _tok(tmp_path):
    path = tmp_path / "tok"
    path.write_text(TOKEN + "\n")
    path.chmod(0o600)
    return path


@needs_backend
def test_token_is_absent_from_logs_traces_files_and_git_config(tmp_path, remote, server):
    srv = server()
    traces = {"GIT_TRACE": "1", "GIT_CURL_VERBOSE": "1", "GIT_TRACE_CURL": "1", "GIT_TRACE_PACKET": "1"}
    env = env_for(tmp_path, srv.url, BND_TOKEN_FILE=str(_tok(tmp_path)), **traces)
    done = subprocess.run(["bash", str(OBS / "sync.sh")], cwd=ROOT, env=env, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    logs = done.stdout + done.stderr
    assert "Authorization" in logs                            # urmele chiar conțin antetul, dar mascat de git
    assert TOKEN not in logs and ENCODED not in logs
    for name in ("sync.json", "sync.attempt"):
        assert not (tmp_path / "data" / name).exists() or TOKEN not in (tmp_path / "data" / name).read_text()
    for base in (tmp_path / "data", tmp_path / "home"):
        for path in base.rglob("*"):
            if path.is_file() or path.is_symlink():
                try:
                    blob = path.read_bytes()
                except OSError:
                    continue
                assert TOKEN.encode() not in blob and ENCODED.encode() not in blob, path
    assert "GIT_TRACE_REDACT" not in "".join(p.read_text() for p in OBS.glob("*.sh"))     # redactarea nu e dezactivată


@needs_backend
def test_credential_helper_cannot_persist_the_token(tmp_path, remote, server):
    """Control + remediere: cu `credential.helper=store` în config-ul utilizatorului, un git simplu ar salva tokenul."""
    srv = server()
    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitconfig").write_text("[credential]\\n\\thelper = store\\n".replace("\\\\n", "\\n").replace("\\n", "\n").replace("\\t", "\t"))
    base = env_for(tmp_path, srv.url, BND_TOKEN_FILE=str(_tok(tmp_path)))
    plain = subprocess.run(["git", "ls-remote", srv.url, "refs/heads/cont-unic"], capture_output=True, text=True,
                           env={**base, "GIT_ASKPASS": str(OBS / "askpass.sh"), "GIT_TERMINAL_PROMPT": "0"})
    assert plain.returncode == 0, plain.stderr
    assert TOKEN in (home / ".git-credentials").read_text()   # controlul: fără protecție, tokenul ar fi ajuns pe disc
    (home / ".git-credentials").unlink()
    done = subprocess.run(["bash", str(OBS / "sync.sh")], cwd=ROOT, env=base, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert not (home / ".git-credentials").exists() and not (home / ".config/git/credentials").exists()


@needs_backend
def test_bootstrap_and_check_token_use_askpass_and_leave_no_credentials(tmp_path, remote, server):
    srv = server()
    tokfile = _tok(tmp_path)
    env = env_for(tmp_path, srv.url, BND_TOKEN_FILE=str(tokfile))
    dest = tmp_path / "clone"
    boot = subprocess.run(["bash", str(OBS / "bootstrap.sh"), str(dest)], capture_output=True, text=True, env=env)
    assert boot.returncode == 0, boot.stderr
    config = (dest / ".git" / "config").read_text()
    assert TOKEN not in config and ENCODED not in config and "x-access-token" not in config and "extraheader" not in config
    chk = subprocess.run(["bash", str(OBS / "check-token.sh")], capture_output=True, text=True, env=env)
    assert chk.returncode == 0, chk.stdout + chk.stderr
    assert "funcționează" in chk.stdout and TOKEN not in chk.stdout + chk.stderr
    wrong = tmp_path / "wrong"
    wrong.write_text("github_pat_gresit\n")
    wrong.chmod(0o600)
    bad = subprocess.run(["bash", str(OBS / "check-token.sh")], capture_output=True, text=True, env={**env, "BND_TOKEN_FILE": str(wrong)})
    assert bad.returncode == 1 and "nu pot citi ramura" in bad.stdout


@needs_backend
def test_systemd_credential_directory_is_used_when_no_token_file_is_set(tmp_path, remote, server):
    srv = server()
    creds = tmp_path / "creds"
    creds.mkdir()
    (creds / "github-token").write_text(TOKEN + "\n")
    env = env_for(tmp_path, srv.url, CREDENTIALS_DIRECTORY=str(creds))
    done = subprocess.run(["bash", str(OBS / "sync.sh")], cwd=ROOT, env=env, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert f"Basic {ENCODED}" in srv.seen


def run_askpass(prompt, tokfile):
    return subprocess.run(["bash", str(OBS / "askpass.sh"), prompt], capture_output=True, text=True,
                          env={**os.environ, "BND_TOKEN_FILE": str(tokfile)})


def test_askpass_answers_only_username_and_password_prompts(tmp_path):
    tok = _tok(tmp_path)
    assert run_askpass("Username for 'https://github.com': ", tok).stdout.strip() == "x-access-token"
    assert run_askpass("Password for 'https://x-access-token@github.com': ", tok).stdout.strip() == TOKEN
    other = run_askpass("Enter passphrase for key '/root/.ssh/id_rsa': ", tok)
    assert other.returncode != 0 and TOKEN not in other.stdout + other.stderr
    missing = run_askpass("Password for 'https://github.com': ", tmp_path / "nu-exista")
    assert missing.returncode != 0 and TOKEN not in missing.stdout


def test_service_hardening_is_documented_with_a_least_privilege_credential_option():
    docs = (ROOT / "docs/PROXMOX.md").read_text()
    for needle in ("GIT_ASKPASS", "GIT_CONFIG_VALUE_0", "/proc", "LoadCredential", "credential.helper", "askpass.sh"):
        assert needle in docs, needle
    example = (OBS / "bnd-observer-credential.conf.example").read_text()
    assert "LoadCredential=github-token:/etc/bnd-observer/github-read-token" in example


# ===================================================================== 2. SINCRONIZARE ÎNTRERUPTĂ ===========

def start_sync(tmp_path, remote_url, pause_at=None, **extra):
    env = env_for(tmp_path, remote_url, **extra)
    if pause_at:
        env["BND_SYNC_PAUSE_AT"] = pause_at
    return subprocess.Popen(["bash", str(OBS / "sync.sh")], cwd=ROOT, env=env, start_new_session=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def run_sync(tmp_path, remote_url, **extra):
    proc = start_sync(tmp_path, remote_url, **extra)
    out = proc.communicate(timeout=60)[0]
    return proc.returncode, out


def wait_lock_free(data, seconds=10):
    """Lacătul .sync.lock se eliberează asincron, când moare și ultimul proces din grup (de exemplu `sleep`)."""
    import fcntl
    deadline = time.time() + seconds
    while time.time() < deadline:
        with open(data / ".sync.lock", "a+") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except OSError:
                pass
        time.sleep(0.05)


def kill_at(tmp_path, remote_url, stage, sig=signal.SIGKILL):
    proc = start_sync(tmp_path, remote_url, pause_at=stage)
    reached = tmp_path / "data" / f".reached.{stage}"
    deadline = time.time() + 30
    while not reached.exists() and time.time() < deadline:
        time.sleep(0.02)
    assert reached.exists(), f"etapa {stage} nu a fost atinsă"
    os.killpg(proc.pid, sig)
    proc.wait(timeout=20)
    wait_lock_free(tmp_path / "data")


def read_status(tmp_path, remote_url="x"):
    out = tmp_path / "status.json"
    done = subprocess.run([sys.executable, "-m", "src.bnd.observer", "--mirror", str(tmp_path / "data/mirror"), "--out", str(out),
                           "--sync-file", str(tmp_path / "data/sync.json")], cwd=ROOT,
                          env={**env_for(tmp_path, remote_url), "BND_OBSERVER_ONLY": "true"}, capture_output=True, text=True)
    return done.returncode, json.loads(out.read_text())


def state(tmp_path):
    return json.loads((tmp_path / "data/sync.json").read_text())


def leftovers(tmp_path):
    data = tmp_path / "data"
    names = [p.name for p in data.iterdir()]
    return [n for n in names if n.startswith((".work.", ".mirror.tmp", ".prev.tmp", ".reached."))] + \
        (["sync.attempt"] if (data / "sync.attempt").exists() else [])


@pytest.mark.parametrize("stage", ["fetch", "before_verify", "after_verify", "after_switch"])
def test_abrupt_kill_is_detected_keeps_the_last_valid_mirror_and_never_looks_like_success(tmp_path, remote, stage):
    bare, work = remote
    assert run_sync(tmp_path, bare)[0] == 0
    first_commit, first_time = state(tmp_path)["mirror_commit"], state(tmp_path)["last_successful_sync"]
    assert first_commit == head(bare)
    time.sleep(1.1)
    push_new_day(work, 11250.0)
    new_commit = head(bare)
    kill_at(tmp_path, bare, stage)                                  # SIGKILL: fără trap, fără curățenie
    # --- înainte de orice nouă rulare: statusul NU spune „sincronizare reușită” și oglinda e întreagă
    code, status = read_status(tmp_path)
    assert status["data_ok"] is True                                # nicio oglindă pe jumătate scrisă
    assert status["sync_ok"] is False and status["sync_interrupted"] is True and status["ok"] is False
    assert status["verdict"] == "sync_failed" and code == observer.EXIT["sync_failed"]
    assert status["last_successful_sync"] == first_time             # ora ultimei sincronizări reale nu s-a mișcat
    expected = new_commit if stage == "after_switch" else first_commit    # comutarea atomică: ori veche, ori nouă, întreagă
    assert status["mirror_commit"] == expected
    assert subprocess.run(["bash", str(OBS / "healthcheck.sh")], capture_output=True,
                          env={**env_for(tmp_path, bare), "BND_DATA_DIR": str(tmp_path / "data")}).returncode != 0
    assert leftovers(tmp_path)                                      # resturile tentativei există și sunt detectate
    # --- următoarea rulare: detectează, înregistrează, curăță, apoi reușește
    rc, out = run_sync(tmp_path, bare)
    assert rc == 0 and "întreruptă" in out
    final = state(tmp_path)
    assert final["interrupted_attempts"] == 1 and final["last_interrupted"] and final["sync_ok"] is True
    assert final["consecutive_failures"] == 0 and final["mirror_commit"] == new_commit
    assert final["last_successful_sync"] > first_time
    assert leftovers(tmp_path) == []
    assert len(list((tmp_path / "data/releases").iterdir())) <= 2
    code, status = read_status(tmp_path)
    assert status["ok"] is True and status["sync_ok"] is True and code == 0


def test_a_running_sync_is_not_reported_as_interrupted(tmp_path, remote):
    bare, _ = remote
    assert run_sync(tmp_path, bare)[0] == 0
    proc = start_sync(tmp_path, bare, pause_at="before_verify")
    reached = tmp_path / "data/.reached.before_verify"
    deadline = time.time() + 30
    while not reached.exists() and time.time() < deadline:
        time.sleep(0.02)
    try:
        assert (tmp_path / "data/sync.attempt").exists()
        assert observer.attempt_interrupted(tmp_path / "data") is False           # lacăt ținut = în curs
        _, status = read_status(tmp_path)
        assert not status.get("sync_interrupted") and status["sync_ok"] is True
    finally:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=20)
    wait_lock_free(tmp_path / "data")
    assert observer.attempt_interrupted(tmp_path / "data") is True                # proces mort = întrerupt


def test_sigterm_is_recorded_as_a_failed_attempt_with_cleanup(tmp_path, remote):
    bare, work = remote
    assert run_sync(tmp_path, bare)[0] == 0
    push_new_day(work, 11300.0)
    kill_at(tmp_path, bare, "before_verify", sig=signal.SIGTERM)
    s = state(tmp_path)
    assert s["sync_ok"] is False and s["sync_error"] == "intrerupt_semnal" and s["consecutive_failures"] == 1
    assert leftovers(tmp_path) == [] or leftovers(tmp_path) == [".reached.before_verify"]
    _, status = read_status(tmp_path)
    assert status["data_ok"] is True and status["sync_ok"] is False and not status.get("sync_interrupted")


def test_missing_mirror_link_is_recovered_from_the_newest_valid_release_even_if_remote_is_down(tmp_path, remote):
    bare, _ = remote
    assert run_sync(tmp_path, bare)[0] == 0
    good = head(bare)
    (tmp_path / "data/mirror").unlink()                              # ca după o oprire în mijlocul unei migrări
    (tmp_path / "data/mirror.prev").unlink(missing_ok=True)
    rc, out = run_sync(tmp_path, tmp_path / "nu-exista.git")
    assert rc == 1 and "recuperată din releases" in out
    _, status = read_status(tmp_path)
    assert status["data_ok"] is True and status["mirror_commit"] == good
    assert status["sync_ok"] is False and status["sync_error"] == "remote_indisponibil"        # recuperarea ≠ sincronizare


def test_legacy_directory_mirror_is_migrated_without_losing_it(tmp_path, remote):
    bare, work = remote
    assert run_sync(tmp_path, bare)[0] == 0
    data = tmp_path / "data"
    target = data / (data / "mirror").readlink()
    (data / "mirror").unlink()
    (data / "mirror.prev").unlink(missing_ok=True)
    target.rename(data / "mirror")                                    # aspectul vechi: folder real, nu legătură
    push_new_day(work, 11400.0)
    assert run_sync(tmp_path, bare)[0] == 0
    assert (data / "mirror").is_symlink() and (data / "mirror.prev").is_symlink()
    assert (data / "mirror" / "COMMIT").read_text().strip() == head(bare)
    assert (data / "mirror.prev" / "paper.sqlite").is_file()


def test_record_sync_interrupted_counts_separately_and_keeps_last_success(tmp_path):
    t0 = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    observer.record_sync(tmp_path, True, now=t0)
    one = observer.record_sync(tmp_path, False, interrupted=True, now=t0.replace(hour=11))
    two = observer.record_sync(tmp_path, False, interrupted=True, now=t0.replace(hour=12))
    assert one["interrupted_attempts"] == 1 and two["interrupted_attempts"] == 2
    assert two["sync_ok"] is False and two["last_successful_sync"] == t0.isoformat(timespec="seconds")
    assert two["sync_error"] == "tentativa_anterioara_intrerupta"
    ok = observer.record_sync(tmp_path, True, now=t0.replace(hour=13))
    assert ok["interrupted_attempts"] == 2 and ok["consecutive_failures"] == 0           # istoricul rămâne


def test_sync_swap_is_atomic_by_construction():
    text = (OBS / "sync.sh").read_text()
    assert "mv -T" in text and "ln -sfn" in text
    assert 'rm -rf "$DATA/mirror.prev"' not in text and 'mv "$DATA/mirror" "$DATA/mirror.prev"' not in text   # vechiul schimb în doi pași
