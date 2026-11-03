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


def test_council_versus_rule_counts_agreement_and_what_the_differences_earned(tmp_path):
    same = ("SP500", {"gpt": ("BUY", .8)}, "BUY", 0.02, 1)
    opposite_right = ("GOLD", {"gpt": ("SELL", .8)}, "SELL", -0.03, 1)      # regula: cumpără; consiliul: vinde, corect
    abstain_saved = ("XRP", {"gpt": ("HOLD", .5)}, "HOLD", -0.04, 1)        # consiliul s-a abținut, regula ar fi pierdut
    alone = ("ETH", {"gpt": ("BUY", .8)}, "BUY", 0.01, 0)
    reg = make_registry(tmp_path, [same] * 18 + [opposite_right, abstain_saved, alone])
    v = fr.council_analytics.analyse(reg)["vs_rule"]

    assert (v["comparable"], v["same"], v["opposite"], v["abstain"]) == (20, 18, 1, 1)
    assert v["agreement_rate"] == 0.9 and v["opposite_council_wins"] == 1 and v["opposite_rule_wins"] == 0
    assert round(v["abstain_rule_mean_pct"], 6) == -4.0 and v["council_only_calls"] == 1
    assert round(v["differ_mean_pct"], 6) == 3.5 and "au adus bani" in v["verdict"]


def test_council_that_only_repeats_the_rule_is_called_out(tmp_path):
    reg = make_registry(tmp_path, [("SP500", {"gpt": ("BUY", .8)}, "BUY", 0.02, 1)] * 20 +
                        [("GOLD", {"gpt": ("SELL", .8)}, "SELL", 0.03, 1)])
    v = fr.council_analytics.analyse(reg)["vs_rule"]
    assert v["agreement_rate"] > 0.9 and "repetă în mare regula" in v["verdict"]


def test_report_has_the_council_versus_rule_section(tmp_path):
    unic = make_account(tmp_path, [10_100])
    registry = make_registry(tmp_path, [("SP500", {"gpt": ("BUY", .8)}, "BUY", 0.01, 1)])
    assert fr.main(["--unic", str(unic), "--registry", str(registry), "--out", str(tmp_path / "r")]) == 0
    md = (tmp_path / "r.md").read_text(encoding="utf-8")
    assert "Consiliul față de regula simplă" in md and "La fel ca regula" in md and "fără concluzie" in md


def test_unified_account_is_compared_with_the_rules_only_control_on_the_same_window(tmp_path):
    unic = make_account(tmp_path, [10_100, 10_200, 10_403])          # 1.11, 2.11, 3.11
    (tmp_path / "c").mkdir()
    ctrl_path = tmp_path / "c" / "paper.sqlite"
    engine = PaperEngine.create(ctrl_path, 10_000.0, currency="USD", now=datetime(2026, 11, 2, tzinfo=timezone.utc))
    for i, eq in enumerate([10_000, 10_100]):                       # 2.11, 3.11
        when = datetime(2026, 11, 2, 23, tzinfo=timezone.utc) + timedelta(days=i)
        engine.record("daily_run", {"time": when.isoformat(), "equity": eq}, when)
    engine.close()

    c = fr.control_comparison(fr.account(unic), fr.account(ctrl_path))
    assert c["from"] == "2026-11-02" and round(c["unic_pct"], 6) == 3.0      # de la 10 100 (1.11) la 10 403
    assert round(c["control_pct"], 6) == 1.0 and round(c["diff_pct"], 6) == 2.0
    assert fr.control_comparison(fr.account(unic), None) is None

    registry = make_registry(tmp_path, [("SP500", {"gpt": ("BUY", .8)}, "BUY", 0.01, 1)])
    assert fr.main(["--unic", str(unic), "--registry", str(registry), "--control", str(ctrl_path), "--out", str(tmp_path / "r")]) == 0
    md = (tmp_path / "r.md").read_text(encoding="utf-8")
    assert "Doar reguli (control)" in md and "a adus un plus" in md
