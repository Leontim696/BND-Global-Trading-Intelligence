"""Raportul orar: o dată pe oră (minute GitHub limitate) și postare pe toată durata testului prelungit."""
from pathlib import Path

TEXT = Path(".github/workflows/rapoarte-bot.yml").read_text(encoding="utf-8")


def test_runs_hourly_only_to_save_github_minutes():
    assert "- cron: '0 * * * *'" in TEXT and "- cron: '30 * * * *'" not in TEXT


def test_reports_keep_being_saved_until_the_end_of_the_30_day_test():
    assert '-le 31 ]' in TEXT and '-le 17 ]' not in TEXT
