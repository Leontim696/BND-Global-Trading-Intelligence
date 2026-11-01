"""Dezbatere în umbră: declanșator, prompt, registru separat, înainte/după."""

import json
from datetime import timedelta
from decimal import Decimal

from src.bnd import council_analytics as ca
from src.bnd import council_daily as cd
from src.bnd import council_debate as db
from src.bnd.ai_gateway import AIGateway, AIResponse, GatewayMode
from src.bnd.decision_registry import DecisionRegistry
from src.bnd.fusion_council import AGENTS, Opinion, Vote
from tests.test_council_daily import MARKETS, series, upto  # noqa: F401


def ops(votes):
    return {a: Opinion(a, Vote(v), f"motiv {a}", c) for a, (v, c) in zip(AGENTS, votes)}


def test_trigger_needs_direct_opposition_or_a_strong_lone_vote():
    assert db.trigger(ops([("BUY", .6), ("SELL", .7)] + [("HOLD", .5)] * 3))["reason"].startswith("opoziție")
    lone = db.trigger(ops([("SELL", .8)] + [("HOLD", .5)] * 4))
    assert lone["reason"].startswith("vot izolat") and lone["strength"] == .8
    assert lone["strength"] < db.trigger(ops([("BUY", .6), ("SELL", .6)] + [("HOLD", .5)] * 3))["strength"]


def test_weak_or_unopposed_votes_do_not_trigger():
    assert db.trigger(ops([("HOLD", .9)] * 5)) is None
    assert db.trigger(ops([("SELL", .65)] + [("HOLD", .5)] * 4)) is None          # prea puțin sigur
    assert db.trigger(ops([("BUY", .9)] * 3 + [("HOLD", .5)] * 2)) is None        # directional majoritar: nu e „izolat”
    assert db.trigger(ops([("BUY", .8)] + [("HOLD", .5)] * 3)) is None            # incomplet: 4 agenți


def market(name, votes):
    return {"market": name, "status": "ok", "last_candle": "2099-01-01",
            "agents": {a: {"vote": v, "confidence": c, "reasoning": f"{a} zice {v}"}
                       for a, (v, c) in zip(AGENTS, votes)}}


def test_select_keeps_the_strongest_markets_up_to_the_limit():
    report = {"markets": [
        market("A", [("BUY", .6), ("SELL", .6)] + [("HOLD", .5)] * 3),
        market("B", [("BUY", .9), ("SELL", .9)] + [("HOLD", .5)] * 3),
        market("C", [("HOLD", .5)] * 5),
        {"market": "D", "status": "incomplet", "agents": {}}]}
    picked = db.select(report, limit=1)
    assert [p["market"] for p in picked] == ["B"]
    assert [p["market"] for p in db.select(report, limit=5, skip={"B"})] == ["A"]


def test_debate_context_includes_every_opinion_and_the_instruction():
    text = db.debate_context("BAZA", ops([("BUY", .6), ("SELL", .7)] + [("HOLD", .5)] * 3))
    assert text.startswith("BAZA") and "DOAR dacă un argument concret" in text
    assert all(a in text for a in AGENTS)


def test_run_debates_records_in_a_separate_registry_with_both_votes(tmp_path, series):
    data = upto(series, 700)
    day = data["SP500"][-1].open_time + timedelta(days=1)
    report = {"time": day.isoformat(), "markets": [
        {**market("SP500", [("BUY", .8), ("SELL", .8)] + [("HOLD", .5)] * 3),
         "last_candle": data["SP500"][-1].open_time.date().isoformat()}]}
    registry = DecisionRegistry(tmp_path / "d.sqlite")
    result = db.run_debates(report, data, cd.simulated_gateway(), registry, day, Decimal("0.6"))
    assert result["candidates"] == 1 and result["markets"][0]["status"] == "ok"
    decision_id = f"{day.date().isoformat()}:SP500"
    assert registry.meta(decision_id)["shadow"] == "debata"
    import sqlite3
    stages = {r[0] for r in sqlite3.connect(tmp_path / "d.sqlite").execute("SELECT DISTINCT stage FROM votes")}
    assert stages == {"initial", "final"}
    again = db.run_debates(report, data, cd.simulated_gateway(), registry, day, Decimal("0.6"))
    assert again["candidates"] == 0                      # nu se plătește de două ori
    assert "Cost total" in db.render(result)


def test_debate_uses_only_candles_up_to_the_original_round(tmp_path, series):
    data = upto(series, 710)                           # azi sunt mai multe zile decât la runda 1
    cut = data["SP500"][699].open_time
    day = cut + timedelta(days=1)
    seen = []

    class Spy:
        def __init__(self, agent): self.agent = agent
        def expected_model(self): return "spy"
        def analyze(self, request):
            seen.append(request.context)
            return AIResponse(self.agent, Vote.HOLD, "ok", 0.6, "spy", 0, 0)

    gateway = AIGateway(GatewayMode.MOCK)
    for a in AGENTS:
        gateway.register(a, Spy(a))
    report = {"time": day.isoformat(), "markets": [
        {**market("SP500", [("BUY", .8), ("SELL", .8)] + [("HOLD", .5)] * 3), "last_candle": cut.date().isoformat()}]}
    db.run_debates(report, data, gateway, DecisionRegistry(tmp_path / "d.sqlite"), day, Decimal("0.6"))
    assert seen and all(cut.date().isoformat() in c for c in seen)
    later = data["SP500"][705].open_time.date().isoformat()
    assert all(later not in c for c in seen)


def test_before_after_counts_flips_and_their_effect():
    def d(outcome, initial, final):
        return {"outcome": outcome, "votes": {a: {"initial": (i, .6), "final": (f, .6)}
                                              for a, i, f in zip(AGENTS, initial, final)}}
    decisions = {
        "a": d(0.02, ["SELL", "SELL", "HOLD", "HOLD", "HOLD"], ["BUY", "BUY", "HOLD", "HOLD", "HOLD"]),  # a ajutat
        "b": d(0.02, ["BUY", "BUY", "HOLD", "HOLD", "HOLD"], ["SELL", "SELL", "HOLD", "HOLD", "HOLD"]),  # a stricat
        "c": d(-0.02, ["SELL", "HOLD", "HOLD", "HOLD", "HOLD"], ["SELL", "HOLD", "HOLD", "HOLD", "HOLD"]),
    }
    r = ca.before_after(decisions)
    assert (r["lean_changed"], r["improved"], r["worsened"]) == (2, 1, 1)
    assert r["initial"]["calls"] == 3 and r["final"]["calls"] == 3
    assert ca.before_after({})["note"]


def test_cli_settle_only_and_mock_run(tmp_path, series, capsys):
    from src.bnd.market_data import save_csv
    data = upto(series, 700)
    for name, candles in data.items():
        save_csv(candles, tmp_path / f"{name}.csv")
    day = data["SP500"][-1].open_time + timedelta(days=1)
    report_path = tmp_path / "raport.json"
    report_path.write_text(json.dumps({"time": day.isoformat(), "markets": [
        {**market("SP500", [("BUY", .8), ("SELL", .8)] + [("HOLD", .5)] * 3),
         "last_candle": data["SP500"][-1].open_time.date().isoformat()}]}))
    reg = str(tmp_path / "d.sqlite")
    assert db.main(["--mode", "mock", "--report", str(report_path), "--data-dir", str(tmp_path),
                    "--registry", reg, "--out", str(tmp_path / "o.md")]) == 0
    assert (tmp_path / "o.md").exists()
    assert db.main(["--settle-only", "--data-dir", str(tmp_path), "--registry", reg]) == 0
    assert db.main(["--mode", "live", "--report", str(report_path), "--data-dir", str(tmp_path),
                    "--registry", reg]) == 2                       # live cere --costs
    assert db.main(["--needed", "--report", str(report_path), "--registry", reg, "--data-dir", str(tmp_path)]) == 0
    assert "SP500" in capsys.readouterr().out          # SP500 face parte din piețele de context
    assert db.main(["--max", "99", "--report", str(report_path), "--data-dir", str(tmp_path),
                    "--registry", reg]) == 2
    capsys.readouterr()
