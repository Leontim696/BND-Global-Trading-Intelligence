"""Analiza agenților (propunerea 4): regim, orizont, supraîncredere, ponderare pe date nevăzute."""

from datetime import date, timedelta

from src.bnd import council_analytics as ca
from src.bnd.fusion_council import AGENTS
from tests.test_council_daily import MARKETS, series, upto  # noqa: F401


def decision(day, symbol, outcome, votes, regime=None, horizon=5, final=None):
    v = {a: {"initial": votes.get(a, ("HOLD", 0.5))} for a in AGENTS}
    if final:
        for a, vote in final.items():
            v[a]["final"] = vote
    return {"symbol": symbol, "vote": "HOLD", "uncertain": True, "outcome": outcome, "day": day,
            "horizon": horizon, "meta": {"regime": regime} if regime else {}, "votes": v}


def many(n_days, good="gpt", bad="claude"):
    """`good` mereu corect, `bad` mereu greșit și încrezător."""
    start = date(2026, 11, 1)
    out = {}
    for i in range(n_days):
        day = (start + timedelta(days=i)).isoformat()
        for m in range(3):
            up = (i + m) % 2 == 0
            outcome = 0.02 if up else -0.02
            right, wrong = ("BUY", "SELL") if up else ("SELL", "BUY")
            out[f"{day}:{m}"] = decision(day, f"M{m}", outcome,
                                         {good: (right, 0.6), bad: (wrong, 0.9)}, regime="urcare calmă")
    return out


def test_overconfidence_is_confidence_minus_hit_rate():
    board = ca.agent_scoreboard(many(5))
    assert board["claude"]["overconfidence"] > 0.8        # declară 0.9, nimerește 0
    assert board["gpt"]["overconfidence"] < 0          # declară 0.6, nimerește 1.0
    assert board["claude"]["mean_brier"] > board["gpt"]["mean_brier"]


def test_penalty_lowers_the_overconfident_agents_weight():
    w = ca.penalized_weights(many(30))
    assert w["penalized"]["claude"] < w["base"]["claude"]
    assert abs(sum(w["penalized"].values()) - 1) < 1e-9


def test_by_regime_marks_small_cells_unreliable():
    cells = ca.by_regime({**many(2), "x": decision("2026-12-01", "Z", 0.03, {"gpt": ("BUY", 0.7)})})
    assert cells["gpt"]["urcare calmă"]["hit_rate"] == 1.0
    assert cells["gpt"]["urcare calmă"]["reliable"] is False
    assert "necunoscut" in cells["gpt"]


def test_by_horizon_groups_decisions():
    d = {"a": decision("2026-11-01", "A", 0.02, {"gpt": ("BUY", 0.7)}, horizon=5),
         "b": decision("2026-11-01", "B", -0.02, {"gpt": ("BUY", 0.7)}, horizon=10)}
    result = ca.by_horizon(d)
    assert result["5 zile"]["hit_rate"] == 1.0 and result["10 zile"]["hit_rate"] == 0.0


def test_revision_value_empty_without_debate_and_counts_with_it():
    assert ca.revision_value(many(3))["changed_votes"] == 0
    d = {"a": decision("2026-11-01", "A", 0.02, {"gpt": ("SELL", 0.7)}, final={"gpt": ("BUY", 0.7)})}
    r = ca.revision_value(d)
    assert (r["changed_votes"], r["improved"], r["worsened"]) == (1, 1, 0)


def test_out_of_sample_needs_enough_days():
    r = ca.out_of_sample_weighting(many(4))
    assert r["evaluated"] is False and "minim" in r["note"]


def test_out_of_sample_uses_only_training_days_for_weights():
    r = ca.out_of_sample_weighting(many(40))
    assert r["evaluated"] and r["train_days"] == 24 and r["embargo_days"] == 5 and r["test_days"] == 11
    assert r["weights_from_train"]["gpt"] > r["weights_from_train"]["claude"]
    # Doi agenți opuși se anulează la vot egal (nicio direcție); ponderarea urmează agentul bun.
    assert r["equal"]["calls"] == 0 and r["weighted"]["calls"] > 0
    assert r["weighted"]["hit_rate"] == 1.0


def test_sign_test():
    assert ca._sign_test_p(0, 0) is None
    assert ca._sign_test_p(10, 0) < 0.01
    assert ca._sign_test_p(5, 5) == 1.0


def test_new_decisions_store_the_market_regime(tmp_path, series):
    from datetime import timedelta
    from decimal import Decimal

    from src.bnd import council_daily as cd
    from src.bnd.decision_registry import DecisionRegistry
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    data = upto(series, 700)
    now = data["SP500"][-1].open_time + timedelta(days=1)
    cd.run_markets(data, MARKETS, cd.simulated_gateway(), registry, now, Decimal("0.6"))
    regime = registry.meta(f"{now.date().isoformat()}:SP500")["regime"]
    assert regime in {"urcare calmă", "urcare agitată", "scădere calmă", "scădere agitată"}
