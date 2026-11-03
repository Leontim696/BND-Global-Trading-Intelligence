"""Raportul orar: prețuri la 30 de minute și postare pe toată durata testului prelungit."""
from pathlib import Path

TEXT = Path(".github/workflows/rapoarte-bot.yml").read_text(encoding="utf-8")


def test_runs_every_half_hour_with_a_light_run_at_half_past():
    assert "- cron: '0 * * * *'" in TEXT and "- cron: '30 * * * *'" in TEXT
    assert "light: ${{ github.event.schedule == '30 * * * *' }}" in TEXT
    assert "if: needs.report.outputs.light != 'true'" in TEXT          # fără comentariu nou la :30
    assert 'if [ "$LIGHT" != "true" ]; then cp ../raport/raport.md "rapoarte/${stamp}.md"; fi' in TEXT


def test_reports_keep_being_saved_until_the_end_of_the_30_day_test():
    assert '-le 31 ]' in TEXT and '-le 17 ]' not in TEXT
