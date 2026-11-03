"""Rulările programate: puține pe zi (planul GitHub gratuit are 2.000 de minute pe lună)."""
from pathlib import Path

W = Path(".github/workflows")
REPORT = (W / "rapoarte-bot.yml").read_text(encoding="utf-8")
STATUS = (W / "status.yml").read_text(encoding="utf-8")


def test_price_report_runs_once_a_day():
    assert REPORT.count("- cron:") == 1 and "- cron: '0 5 * * *'" in REPORT


def test_status_twice_a_day_and_phone_alerts_once():
    assert STATUS.count("- cron:") == 2
    assert "if: github.event.schedule != '35 17 * * *'" in STATUS


def test_reports_keep_being_saved_until_the_end_of_the_30_day_test():
    assert '-le 31 ]' in REPORT and '-le 17 ]' not in REPORT
