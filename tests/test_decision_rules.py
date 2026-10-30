"""Tests for Fusion Council decision rules and minority objections."""

import pytest

from src.bnd.debate_engine import DebateArgument, DebateEngine, DebateResponse
from src.bnd.decision_rules import AgentScorebook, DecisionRule, decide
from src.bnd.fusion_council import AGENTS, FusionCouncil, Opinion, Vote
from src.bnd.risk_engine import Portfolio, RiskLimits, TradeProposal
from src.bnd.trade_coordinator import TradeStatus, coordinate_trade


def council(votes, confidences=None):
    confidences = confidences or [0.8] * len(AGENTS)
    result = FusionCouncil()
    for agent, vote, confidence in zip(AGENTS, votes, confidences):
        result.submit(Opinion(agent, vote, f"{agent} analysis", confidence))
    return result


B, S, H = Vote.BUY, Vote.SELL, Vote.HOLD


def test_majority_rule():
    decision = decide(council([B, B, B, S, H]))

    assert decision.vote == B and not decision.uncertain
    assert decision.dissenting == ("grok", "deepseek")


def test_unanimity_rule():
    assert decide(council([B] * 5), DecisionRule.UNANIMITY).vote == B
    split = decide(council([B, B, B, B, S]), DecisionRule.UNANIMITY)
    assert split.vote == H and split.uncertain
    assert "not unanimous" in split.reasons[0]


def test_weighted_rule_counts_confidence_and_weights():
    # Three hesitant BUYs against two confident SELLs.
    votes = council([B, B, B, S, S], [0.56, 0.56, 0.56, 0.95, 0.95])

    weighted = decide(votes, DecisionRule.WEIGHTED)

    # 1.68 vs 1.90: no side reaches 60% support, so HOLD.
    assert weighted.vote == H and weighted.uncertain
    assert weighted.support["SELL"] == pytest.approx(1.90 / 3.58)

    trusted = {"gpt": 0.35, "claude": 0.35, "gemini": 0.2, "grok": 0.05, "deepseek": 0.05}
    assert decide(votes, DecisionRule.WEIGHTED, trusted).vote == B


def test_low_confidence_majority_is_hold():
    decision = decide(council([B, B, B, H, H], [0.5, 0.52, 0.51, 0.9, 0.9]))

    assert decision.vote == H and decision.uncertain
    assert any("confidence" in reason for reason in decision.reasons)


def test_incomplete_council_is_hold():
    partial = FusionCouncil()
    partial.submit(Opinion("gpt", B, "x", 0.9))

    assert decide(partial).vote == H


def test_weights_must_cover_every_agent():
    with pytest.raises(ValueError):
        decide(council([B] * 5), DecisionRule.WEIGHTED, {"gpt": 1.0})


def test_scorebook_rewards_measured_skill_with_shrinkage():
    book = AgentScorebook()
    for _ in range(40):
        book.record("claude", B, 0.8, market_went_up=True)   # right, confident
        book.record("grok", B, 0.8, market_went_up=False)    # wrong, confident
        book.record("gpt", H, 0.9, market_went_up=True)      # HOLD is not scored

    weights = book.weights()

    assert weights["claude"] > weights["gpt"] > weights["grok"]
    assert sum(weights.values()) == pytest.approx(1.0)
    # The worst agent keeps a floor weight: one bad streak does not silence it.
    assert weights["grok"] > 0

    restored = AgentScorebook.from_dict(book.to_dict())
    assert restored.weights() == pytest.approx(weights)


def test_few_outcomes_stay_close_to_equal_weights():
    book = AgentScorebook()
    book.record("claude", B, 0.9, market_went_up=True)

    weights = book.weights()

    assert max(weights.values()) - min(weights.values()) < 0.05


def open_debate(votes):
    debate = DebateEngine(council(votes))
    debate.start()
    return debate


def test_minority_objection_forces_reconsideration_and_keeps_history():
    """Acceptance: one dissenter makes the majority re-examine its votes."""
    debate = open_debate([B, B, B, B, S])
    for agent in AGENTS[:4]:
        debate.submit_argument(DebateArgument(agent, "Trend up", "Breakout above range"))
    # Everyone responds in the first round...
    for agent in AGENTS:
        debate.submit_response(DebateResponse(agent, "Initial view", debate.council.current_opinions()[agent].vote, 0.8))
    # ...then the lone dissenter objects to two majority agents.
    objection = DebateArgument("deepseek", "Breakout is on falling volume",
                               "Volume 40% below 20-day average; prior two breakouts failed",
                               challenges=("gpt", "claude"))
    debate.submit_argument(objection)

    open_items = debate.unanswered_objections()
    assert {item["challenged"] for item in open_items} == {"gpt", "claude"}
    with pytest.raises(ValueError, match="Unanswered objections"):
        debate.close()

    # Claude is persuaded; GPT keeps BUY but must answer.
    debate.submit_response(DebateResponse("claude", "Volume concern is valid", H, 0.6))
    debate.submit_response(DebateResponse("gpt", "Volume falls in every breakout here; keep BUY", B, 0.7))
    debate.close()

    history = debate.council.audit_log()
    assert [v["vote"] for v in history["initial_votes"]] == ["BUY", "BUY", "BUY", "BUY", "SELL"]
    assert {"agent": "claude", "vote": "HOLD"}.items() <= history["revisions"][-2].items()
    assert debate.audit_log()["unanswered_objections"] == []


def test_objection_against_agreeing_agent_needs_no_answer():
    debate = open_debate([B, B, B, B, B])
    for agent in AGENTS:
        debate.submit_argument(DebateArgument(agent, "Up", "Evidence", challenges=("gpt",)))
        debate.submit_response(DebateResponse(agent, "Agree", B, 0.8))

    assert debate.unanswered_objections() == []
    debate.close()


def full_debate(votes, confidences):
    debate = DebateEngine(council(votes, confidences))
    debate.start()
    for agent in AGENTS:
        debate.submit_argument(DebateArgument(agent, "View", "Evidence"))
    for agent, vote, confidence in zip(AGENTS, votes, confidences):
        debate.submit_response(DebateResponse(agent, "Final", vote, confidence))
    debate.close()
    return debate


PORTFOLIO = Portfolio(equity=10_000, daily_loss=0, drawdown=0, gross_exposure=0)
LIMITS = RiskLimits(1.0, 3.0, 10.0, 200.0, 3.0)
PROPOSAL = TradeProposal(notional=2_000, stop_loss_pct=2.0, leverage=1.0)


def test_coordinator_uses_selected_rule():
    debate = full_debate([B, B, B, B, S], [0.8] * 5)

    majority = coordinate_trade(debate, PORTFOLIO, LIMITS, PROPOSAL)
    unanimous = coordinate_trade(debate, PORTFOLIO, LIMITS, PROPOSAL,
                                 rule=DecisionRule.UNANIMITY)

    # 1% risk / 2% stop allows 5,000, so the 2,000 proposal is approved in full.
    assert majority.status == TradeStatus.APPROVED and majority.direction == "BUY"
    assert unanimous.status == TradeStatus.NO_TRADE
    assert "not unanimous" in unanimous.reason


def test_risk_engine_still_vetoes_a_unanimous_council():
    debate = full_debate([B] * 5, [0.95] * 5)
    exhausted = Portfolio(equity=9_000, daily_loss=1_000, drawdown=1_000, gross_exposure=0)

    outcome = coordinate_trade(debate, exhausted, LIMITS, PROPOSAL, rule=DecisionRule.UNANIMITY)

    assert outcome.status == TradeStatus.REJECTED
