"""Reguli de securitate pentru workflow-uri și pagina aplicației (fără PyYAML: doar text)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
WITH_KEY = {"OPENROUTER_API_KEY": {"bnd-five-agent-overnight.yml", "bnd-overnight-ai-review.yml",
                                   "consiliu-umbra.yml", "dezbatere-umbra.yml", "status.yml", "gpt-claude-manual.yml",
                                   "openrouter-secret-check.yml", "three-agents-live.yml"},
            "SOLANATRACKER_API_KEY": {"smart-money.yml", "smart-money-sondaj.yml"}, "FRED_API_KEY": {"date-macro.yml"},
            "NTFY_TOPIC": {"health-check.yml", "status.yml", "test-notificare.yml", "dimineata.yml", "notifica.yml"}}


def text(path):
    return path.read_text(encoding="utf-8")


def test_every_workflow_declares_its_permissions_at_the_top_level():
    for path in WORKFLOWS:
        assert re.search(r"^permissions:\s*$", text(path), re.M), path.name


def test_write_access_is_never_given_to_a_job_that_runs_project_code_with_a_secret():
    for path in WORKFLOWS:
        body = text(path)
        if "secrets." not in body:
            continue
        # Un job cu secret nu are permisiuni de scriere (jobul „publish” e separat și fără secret).
        for job in re.split(r"^  (?=[a-z][\w-]*:\s*$)", body.split("\njobs:", 1)[1], flags=re.M):
            if "secrets." in job:
                assert not re.search(r"(contents|issues|actions|pull-requests):\s*write", job), path.name


def test_secrets_are_used_only_where_expected():
    for path in WORKFLOWS:
        for name in re.findall(r"secrets\.(\w+)", text(path)):
            if name == "GITHUB_TOKEN":
                continue
            assert name in WITH_KEY and path.name in WITH_KEY[name], f"{name} în {path.name}"


def test_no_dangerous_triggers():
    for path in WORKFLOWS:
        body = text(path)
        assert "pull_request_target" not in body, path.name
        assert "workflow_run" not in body, path.name


def test_untrusted_expressions_never_land_inside_shell_commands():
    expression = re.compile(r"\$\{\{\s*(inputs\.|github\.event\.|github\.head_ref)")
    for path in WORKFLOWS:
        for number, line in enumerate(text(path).splitlines(), 1):
            if expression.search(line):
                # Doar în atribuiri YAML (env, if, with, group), nu în comenzi shell.
                assert re.match(r"^\s*(-\s*)?[A-Za-z_][\w-]*:\s", line), f"{path.name}:{number}: {line.strip()}"


def test_only_official_actions_are_used():
    for path in WORKFLOWS:
        for owner in re.findall(r"uses:\s*([\w.-]+)/", text(path)):
            assert owner == "actions", f"{path.name}: {owner}"


def test_runtime_has_no_third_party_dependencies():
    lines = [line.strip() for line in text(ROOT / "requirements.txt").splitlines()
             if line.strip() and not line.startswith("#")]
    # Singura excepție: tzdata, doar pe Windows (fusurile orare din morning.py).
    assert all(line.startswith("pytest") or line.startswith('tzdata>=') and "sys_platform == \"win32\"" in line
               for line in lines), lines
    assert (ROOT / ".github" / "dependabot.yml").exists()


def test_dashboard_template_escapes_every_data_string():
    html = text(ROOT / "src" / "bnd" / "dashboard_template.html")
    fields = ("symbol", "title", "subtitle", "kill_reason", "currency", "day")
    for number, line in enumerate(html.splitlines(), 1):
        for field in fields:
            for match in re.finditer(r"\$\{([^}]*\.%s\b[^}]*)\}" % field, line):
                assert match.group(1).lstrip().startswith("esc("), f"linia {number}: {match.group(0)}"
    assert 'class="v ${esc(v)}"' in html
    assert "</" not in "".join(re.findall(r"const DATA = (.*);", html))


def test_branch_cleanup_protects_every_state_branch_and_has_write_only_in_its_job():
    body = text(ROOT / ".github" / "workflows" / "branch-cleanup.yml")
    assert re.search(r"^permissions:\n  contents: read", body, re.M)
    for branch in ("backtest-results", "paper-trading", "crypto-trading", "ai-unificat",
                   "consiliu-umbra", "status", "date-piete", "reguli-ls", "cont-unic"):
        assert body.count(branch) >= 2, branch              # în ambele liste de protecție
    # Orice ramură de stare folosită de un workflow trebuie să fie protejată.
    used = set()
    for path in WORKFLOWS:
        used |= set(re.findall(r"origin\s+(paper-trading|crypto-trading|ai-unificat|consiliu-umbra|status|backtest-results|date-piete|reguli-ls|cont-unic)\b",
                               text(path)))
    assert all(branch in body for branch in used), used


def test_every_action_is_pinned_to_a_full_commit_hash_with_its_version_in_a_comment():
    for path in WORKFLOWS:
        for number, line in enumerate(text(path).splitlines(), 1):
            if "uses:" in line and "@" in line:
                assert re.search(r"uses:\s*actions/[\w-]+(/[\w-]+)?@[0-9a-f]{40}\s+#\s*v\d+\s*$", line), \
                    f"{path.name}:{number}: {line.strip()}"
