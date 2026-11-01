"""Lista albă pentru argumentele libere din workflow-uri (audit #29)."""

import re
from pathlib import Path

import pytest

from scripts import safe_args as sa

ROOT = Path(__file__).resolve().parents[1]


def test_valid_settings_pass_unchanged():
    text = "--strategy regime_switch --portfolio-vol 15 --max-leverage 3 --financing 5"
    assert sa.validate(text) == text.split()
    assert sa.validate("--no-shorts --base-currency EUR --universe unic") == ["--no-shorts", "--base-currency", "EUR", "--universe", "unic"]
    assert sa.validate("--max-leverage=2.5") == ["--max-leverage", "2.5"]
    assert sa.validate("") == [] and sa.validate("   ") == []
    assert sa.validate("--range fast=10:50:10 --param fast=20 --members sma_crossover,momentum") != []


@pytest.mark.parametrize("bad", [
    "--state /tmp/other.sqlite", "--report ../../x.md", "--audit-log /dev/null", "--data-dir /etc",
    "--signals evil.json", "--out x", "--reset-kill-switch CONFIRM", "--capital 1000000",
    "--strategy ../../x", "--strategy x;rm", "--max-leverage abc", "--max-leverage", "--max-leverage 3 --nope",
    "--base-currency JPY", "--universe weird", "--markets 'A B'", "--param a=$(id)", "$(touch /tmp/x)",
    "--strategy 'unclosed", "--max-leverage 1e9", "--markets " + "A," * 200 + "B",
])
def test_unsafe_input_is_refused(bad):
    with pytest.raises(sa.UnsafeArguments):
        sa.validate(bad)


def test_cli_exit_codes(capsys):
    assert sa.main(["--max-leverage 3"]) == 0 and capsys.readouterr().out.strip() == "--max-leverage 3"
    assert sa.main(["--state x"]) == 2 and "refuzate" in capsys.readouterr().err
    assert sa.main([]) == 2


def test_every_free_text_workflow_input_goes_through_the_allow_list():
    for name in ("backtest", "portfolio", "paper-trading", "reguli-ls"):
        text = (ROOT / ".github" / "workflows" / f"{name}.yml").read_text()
        assert "scripts/safe_args.py" in text, name
        assert not re.search(r"args\+=\(\$SETTINGS\)", text), name
        if name in ("backtest", "portfolio"):
            assert "RAW_EXTRA_ARGS" in text and 'echo "EXTRA_ARGS=$safe"' in text, name


def test_remaining_or_true_are_only_the_benign_patterns():
    allowed = ("git checkout -q --orphan", "cp -r", "2>/dev/null || true")
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if "|| true" in line:
                assert any(p in line for p in allowed), f"{path.name}:{number}: {line.strip()}"


def test_status_job_does_not_hold_secrets_for_the_project_code_steps():
    text = (ROOT / ".github" / "workflows" / "status.yml").read_text()
    job_env = text.split("    env:\n", 1)[1].split("    steps:", 1)[0]
    assert "NTFY_TOPIC" not in job_env and "GH_TOKEN" not in job_env


def test_checkouts_that_do_not_need_git_credentials_do_not_keep_them():
    needs = re.compile(r"git fetch|restore_|git ls-remote|git show origin|git archive|git pull|git push|git remote")
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        text = path.read_text()
        if "actions/checkout@" in text and not needs.search(text):
            assert text.count("persist-credentials: false") >= text.count("actions/checkout@"), path.name


def test_a_failed_commit_is_never_hidden():
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        text = path.read_text()
        assert not re.search(r"git commit[^\n]*\|\| true", text), path.name


def test_every_account_workflow_requires_the_audit_chain():
    for name in ("cont-unic", "paper-trading", "reguli-ls", "bot-ai-unificat", "cripto-ai"):
        assert 'REQUIRE_AUDIT: "1"' in (ROOT / ".github" / "workflows" / f"{name}.yml").read_text(), name
    assert '"!audit.jsonl"' in (ROOT / ".github" / "workflows" / "consiliu-umbra.yml").read_text()


def test_paid_review_needs_the_typed_confirmation_and_the_key_only_on_its_step():
    text = (ROOT / ".github" / "workflows" / "bnd-overnight-ai-review.yml").read_text()
    assert "schedule:" not in text and "confirm_paid_test.py" in text
    job_env = text.split("    env:\n", 1)[1].split("    steps:", 1)[0]
    assert "OPENROUTER_API_KEY" not in job_env and "OPENROUTER_API_KEY" in text


def test_budget_defaults_match_everywhere():
    assert "2,50" not in (ROOT / ".github" / "workflows" / "consiliu-umbra.yml").read_text()
    from src.bnd import council_daily
    import argparse
    text = (ROOT / "src" / "bnd" / "council_daily.py").read_text()
    assert '"--daily-budget", default="3.00"' in text and '"--monthly-budget", default="38"' in text


def test_fetch_only_workflows_do_not_persist_credentials():
    for name in ("status", "dimineata", "health-check"):
        text = (ROOT / ".github" / "workflows" / f"{name}.yml").read_text()
        assert "persist-credentials: false" in text and "extraheader" in text, name
        job_env = text.split("    env:\n", 1)[1].split("    steps:", 1)[0]
        assert "GH_TOKEN" not in job_env and "NTFY_TOPIC" not in job_env, name
