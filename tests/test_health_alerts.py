"""Monitorizarea nu spune „sănătos” când n-a putut citi starea (audit #8)."""

from src.bnd import notify
from src.bnd.health_check import check, main
from tests.test_health_check import START, account_after_one_run


def test_unreadable_account_is_a_problem_not_a_green_check(tmp_path):
    result = check(tmp_path / "lipsa.sqlite", START, state_error="nu pot descărca paper.sqlite")
    assert not result["ok"] and "nu pot descărca" in result["problems"][0]


def test_unknown_last_run_is_a_problem(tmp_path):
    path, now = account_after_one_run(tmp_path)
    result = check(path, now, last_run_conclusion="unknown")
    assert not result["ok"] and any("starea ultimei rulări" in p for p in result["problems"])
    assert check(path, now, last_run_conclusion="success")["ok"]


def test_cli_passes_state_error(tmp_path, capsys):
    code = main(["--state", str(tmp_path / "x.sqlite"), "--state-error", "rețea căzută",
                 "--json", str(tmp_path / "h.json")])
    assert code == 0
    assert '"ok": false' in (tmp_path / "h.json").read_text()
    assert "rețea căzută" in capsys.readouterr().out


def test_missing_topic_with_require_prints_a_visible_warning(monkeypatch, capsys):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert notify.main(["--title", "t", "--message", "m", "--require"]) == 0
    assert "::warning::" in capsys.readouterr().out
    assert notify.main(["--title", "t", "--message", "m"]) == 0
    assert "::warning::" not in capsys.readouterr().out
