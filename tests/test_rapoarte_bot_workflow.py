"""Raportul orar și bucla de prețuri la 10 minute."""
from pathlib import Path

TEXT = Path(".github/workflows/rapoarte-bot.yml").read_text(encoding="utf-8")


def test_full_report_stays_hourly():
    assert "- cron: '0 * * * *'" in TEXT and "- cron: '30 * * * *'" not in TEXT


LOOP = Path(".github/workflows/preturi-live.yml").read_text(encoding="utf-8")


def test_live_prices_loop_every_10_minutes_restarts_itself_and_keeps_the_token_away_from_project_code():
    assert "left=$(( 600 - " in LOOP and "deadline=$(( $(date +%s) + 340*60 ))" in LOOP
    assert "actions/workflows/preturi-live.yml/dispatches" in LOOP and "- cron: '7 */6 * * *'" in LOOP
    assert 'py() { env -u GH_TOKEN -u b64 python "$@"; }' in LOOP
    assert "python -m" not in LOOP.replace('env -u GH_TOKEN -u b64 python "$@"', "")   # tot codul trece prin py()
    assert "persist-credentials: false" in LOOP and "publish gh-pages page" in LOOP and "orphan" in LOOP


def test_reports_keep_being_saved_until_the_end_of_the_30_day_test():
    assert '-le 31 ]' in TEXT and '-le 17 ]' not in TEXT


def test_ci_audits_dependencies_for_known_vulnerabilities():
    ci = Path(".github/workflows/python-tests.yml").read_text(encoding="utf-8")
    assert "pip-audit==" in ci and "pip-audit -r requirements.txt" in ci


def test_hourly_report_is_saved_but_not_posted_to_the_phone():
    assert "repos/$REPO/issues" not in TEXT and "issues: write" not in TEXT
    assert 'cp ../raport/raport.md rapoarte/LATEST.md' in TEXT          # salvarea rămâne


def test_dashboardul_live_primeste_top50_si_intraday():
    # 5.11: fila „Top 50 crypto” era goală pe GitHub Pages pentru că bucla nu dădea --top50.
    assert "--top50 out/ch/crypto50" in LOOP and "--intraday out/i" in LOOP
