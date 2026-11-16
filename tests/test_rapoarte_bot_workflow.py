"""Raportul orar și bucla de prețuri (la 60 de minute din 9.11.2026)."""
from pathlib import Path

TEXT = Path(".github/workflows/rapoarte-bot.yml").read_text(encoding="utf-8")


def test_full_report_is_started_by_the_live_loop_with_a_cron_fallback():
    # 16.11.2026: GitHub sărea majoritatea rulărilor de la ora fixă; bucla pornește raportul la fiecare ciclu.
    assert "- cron: '23 */3 * * *'" in TEXT and "- cron: '0 * * * *'" not in TEXT
    assert "actions/workflows/rapoarte-bot.yml/dispatches" in LOOP


LOOP = Path(".github/workflows/preturi-live.yml").read_text(encoding="utf-8")


def test_live_prices_loop_every_60_minutes_restarts_itself_and_keeps_the_token_away_from_project_code():
    assert "left=$(( 3600 - " in LOOP and "left=$(( 600 - " not in LOOP and "deadline=$(( $(date +%s) + 290*60 ))" in LOOP
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


def test_intraday_loop_runs_every_60_minutes():
    # 9.11.2026: rărit de la 10 la 60 de minute, la cererea proprietarului, după suspendarea contului GitHub.
    loop = Path(".github/workflows/intraday-10min.yml").read_text(encoding="utf-8")
    assert "left=$(( 3600 - " in loop and "left=$(( 600 - " not in loop
    assert "deadline=$(( $(date +%s) + 290*60 ))" in loop


def _limit_and_deadline(text):
    import re
    timeout = max(int(m) for m in re.findall(r"timeout-minutes: (\d+)", text))
    deadline = int(re.search(r"deadline=\$\(\( \$\(date \+%s\) \+ (\d+)\*60 \)\)", text).group(1))
    return timeout, deadline


def test_loops_finish_their_last_60_minute_cycle_before_the_job_limit_so_they_can_restart():
    # 16.11.2026: ultimul ciclu depășea limita jobului, jobul era anulat și repornirea de la final nu mai rula.
    for name in ("preturi-live.yml", "intraday-10min.yml"):
        timeout, deadline = _limit_and_deadline(Path(".github/workflows/" + name).read_text(encoding="utf-8"))
        assert deadline + 60 + 5 <= timeout, name
