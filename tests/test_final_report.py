"""Raportul final: doar citire, criterii fixe, lipsa datelor spusă explicit."""
from datetime import date, datetime, timedelta, timezone

from src.bnd import final_report as fr
from src.bnd.market_data import Candle, save_csv
from src.bnd.paper_engine import PaperEngine
from tests.test_council_quality import make_registry

NOW = datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc)


def make_account(tmp_path, equities):
    path = tmp_path / "paper.sqlite"
    engine = PaperEngine.create(path, 10_000.0, currency="USD", now=datetime(2026, 10, 31, tzinfo=timezone.utc))
    for i, eq in enumerate(equities):
        when = datetime(2026, 11, 1, 23, tzinfo=timezone.utc) + timedelta(days=i)
        engine.record("daily_run", {"time": when.isoformat(), "equity": eq}, when)
    engine.close()
    return path


def test_account_curve_return_and_drawdown(tmp_path):
    acc = fr.account(make_account(tmp_path, [10_100, 9_595, 10_200]))

    assert acc["days"] == 3 and acc["final"] == 10_200
    assert round(acc["return_pct"], 6) == 2.0
    assert round(acc["max_drawdown_pct"], 6) == 5.0             # 10 100 → 9 595
    assert acc["worst_day_pct"] < 0 < acc["best_day_pct"]


def test_account_reads_without_changing_the_file(tmp_path):
    path = make_account(tmp_path, [10_050])
    before = path.read_bytes()
    fr.account(path)
    assert path.read_bytes() == before


def test_benchmark_uses_the_same_window_and_says_when_data_is_missing(tmp_path):
    days = [datetime(2026, 10, 29, tzinfo=timezone.utc) + timedelta(days=i) for i in range(20)]
    save_csv([Candle(d, 100 + i, 200, 50, 100 + i, 1) for i, d in enumerate(days)], tmp_path / "SP500.csv")

    bench = fr.benchmark(tmp_path / "SP500.csv", date(2026, 10, 31), date(2026, 11, 16))
    assert bench["from"] == "2026-10-30" and bench["to"] == "2026-11-16"
    assert round(bench["return_pct"], 6) == round(100 * (118 / 101 - 1), 6)
    assert fr.benchmark(tmp_path / "SP500.csv", date(2026, 12, 1), date(2026, 12, 5)) is None
    assert fr.benchmark(tmp_path / "lipsa.csv", date(2026, 10, 31), date(2026, 11, 16)) is None


def test_verdict_needs_every_pre_registered_criterion(tmp_path):
    acc = {"return_pct": 3.0}
    many_hits = make_registry(tmp_path, [
        ("SP500", {"gpt": ("BUY", .8), "claude": ("BUY", .8), "gemini": ("BUY", .8)}, "BUY", 0.02, 1)] * 25)
    council = fr.council_analytics.analyse(many_hits)

    assert fr.verdict(acc, {"return_pct": 1.0}, council)["passed"]
    assert not fr.verdict(acc, {"return_pct": 5.0}, council)["passed"]        # nu bate S&P 500
    assert not fr.verdict(acc, None, council)["passed"]                         # fără benchmark = nedovedit
    assert "NU dovadă" in fr.verdict(acc, {"return_pct": 1.0}, council)["text"]


def test_too_few_decisions_never_pass(tmp_path):
    few = make_registry(tmp_path, [
        ("SP500", {"gpt": ("BUY", .8), "claude": ("BUY", .8), "gemini": ("BUY", .8)}, "BUY", 0.02, 1)] * 5)
    v = fr.verdict({"return_pct": 9.0}, {"return_pct": 0.0}, fr.council_analytics.analyse(few))
    assert not v["passed"] and v["text"].startswith("Fără dovezi")


def test_main_writes_markdown_and_escaped_html(tmp_path):
    unic = make_account(tmp_path, [10_100])
    registry = make_registry(tmp_path, [("SP500", {"gpt": ("BUY", .8)}, "BUY", 0.01, 1)])

    assert fr.main(["--unic", str(unic), "--registry", str(registry), "--out", str(tmp_path / "r")]) == 0

    md = (tmp_path / "r.md").read_text(encoding="utf-8")
    page = (tmp_path / "r.html").read_text(encoding="utf-8")
    assert "Fără dovezi de avantaj" in md and "fără date" in md and "Limite" in md
    assert "<script" not in page and "&amp;" in page              # „S&P 500” scăpat corect
    assert fr.main(["--unic", str(tmp_path / "nu-exista.sqlite"), "--registry", str(registry),
                    "--out", str(tmp_path / "x")]) == 1


def test_preliminary_report_uses_the_first_16_days_and_says_the_test_continues(tmp_path):
    unic = make_account(tmp_path, [10_100])
    registry = make_registry(tmp_path, [("SP500", {"gpt": ("BUY", .8)}, "BUY", 0.01, 1)])

    assert fr.main(["--unic", str(unic), "--registry", str(registry), "--out", str(tmp_path / "p"), "--preliminar"]) == 0

    md = (tmp_path / "p.md").read_text(encoding="utf-8")
    assert md.startswith("# Raport preliminar") and "31.10–16.11.2026" in md and "continuă până pe 30.11.2026" in md
    assert fr.TEST_END.isoformat() == "2026-11-30" and fr.PRELIMINARY_END.isoformat() == "2026-11-16"
