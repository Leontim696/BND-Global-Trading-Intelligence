"""Daily health check of the paper account."""

import json
from datetime import timedelta

from src.bnd.health_check import check, main
from src.bnd.paper_engine import PaperEngine
from src.bnd.paper_runner import run_daily
from tests.test_paper_runner import MARKETS, START, config, factory, make_data, now_after


def account_after_one_run(tmp_path):
    data = make_data()
    engine = PaperEngine.create(tmp_path / "paper.sqlite", 10_000, currency="USD", now=START)
    run_daily(engine, data, MARKETS, factory, config(), "sma", now_after(data))
    engine.close()
    return tmp_path / "paper.sqlite", now_after(data)


def test_no_account_yet_is_fine(tmp_path):
    result = check(tmp_path / "none.sqlite", START)

    assert result["ok"] and not result["account"]
    assert "suma de pornire" in result["summary"]["note"]


def test_recent_run_is_fine_and_stale_run_is_a_problem(tmp_path):
    path, ran_at = account_after_one_run(tmp_path)

    assert check(path, ran_at + timedelta(hours=20))["ok"]
    late = check(path, ran_at + timedelta(hours=60))
    assert not late["ok"] and "nu a mai rulat" in late["problems"][0]


def test_kill_switch_and_failed_workflow_are_problems(tmp_path):
    path, ran_at = account_after_one_run(tmp_path)
    engine = PaperEngine.open(path)
    with engine._transaction():
        engine._trip("test stop", ran_at.isoformat())
    engine.close()

    result = check(path, ran_at, last_run_conclusion="failure")

    assert len(result["problems"]) == 2
    assert any("Oprirea de siguranță" in p for p in result["problems"])
    assert any("failure" in p for p in result["problems"])


def test_unreadable_account_is_a_problem(tmp_path):
    bad = tmp_path / "bad.sqlite"
    bad.write_text("not a database")

    result = check(bad, START)

    assert not result["ok"] and "nu poate fi citit" in result["problems"][0]


def test_cli_writes_json_and_markdown(tmp_path, capsys):
    out = tmp_path / "health.json"

    assert main(["--state", str(tmp_path / "none.sqlite"), "--json", str(out)]) == 0
    assert "Totul este în regulă" in capsys.readouterr().out
    assert json.loads(out.read_text())["ok"] is True
