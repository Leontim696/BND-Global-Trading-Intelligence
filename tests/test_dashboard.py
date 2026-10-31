"""Datele aplicației de pe telefon: doar citire, fără rețea."""

from datetime import datetime, timezone

import pytest

from src.bnd import dashboard
from src.bnd.paper_engine import PaperEngine

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


def test_missing_accounts_are_reported_not_fatal(tmp_path):
    data = dashboard.collect(tmp_path, None, None, tmp_path, NOW)

    assert [a["exists"] for a in data["accounts"]] == [False, False, False]
    assert data["council"] == {"exists": False}


def test_existing_account_is_summarised(tmp_path):
    PaperEngine.create(tmp_path / "paper.sqlite", 5_000.0, currency="USD", now=NOW).close()

    data = dashboard.collect(tmp_path, None, None, None, NOW)

    account = data["accounts"][0]
    assert account["exists"] and account["equity"] == 5_000.0
    assert account["positions"] == [] and account["kill_switch"] is False


def test_render_puts_data_in_the_template_and_escapes_script_ends():
    html = dashboard.render({"x": "</script>"}, "<script>const D = /*DATA*/null;</script>")

    assert "</script>\"" not in html.split("const D = ")[1]
    with pytest.raises(ValueError):
        dashboard.render({}, "fără loc pentru date")


def test_real_template_has_the_data_slot():
    from pathlib import Path
    assert "/*DATA*/null" in (Path(dashboard.__file__).parent / "dashboard_template.html").read_text(encoding="utf-8")
