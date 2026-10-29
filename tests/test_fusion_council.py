
"""Tests for BND Fusion Council with five active AI agents."""

import pytest

from src.bnd.fusion_council import (
    AGENTS,
    FusionCouncil,
    Opinion,
    Vote,
)


def make_opinion(agent, vote=Vote.BUY, confidence=0.8):
    return Opinion(
        agent=agent,
        vote=vote,
        reasoning="Independent market analysis",
        confidence=confidence,
    )


def make_council(votes=None):
    if votes is None:
        votes = [Vote.BUY] * len(AGENTS)

    council = FusionCouncil()

    for agent, vote in zip(AGENTS, votes):
        council.submit(make_opinion(agent, vote))

    return council


def test_five_active_agents():
    assert AGENTS == (
        "gpt",
        "claude",
        "gemini",
        "grok",
        "deepseek",
    )


def test_local_ai_not_active():
    assert "local_ai" not in AGENTS

    with pytest.raises(ValueError):
        make_opinion("local_ai")


def test_unanimous_buy():
    council = make_council()

    assert council.decision() == Vote.BUY


def test_three_of_five_buy_majority():
    council = make_council(
        [Vote.BUY] * 3 + [Vote.SELL] * 2
    )

    assert council.decision() == Vote.BUY


def test_three_of_five_sell_majority():
    council = make_council(
        [Vote.SELL] * 3 + [Vote.BUY] * 2
    )

    assert council.decision() == Vote.SELL


def test_no_majority():
    council = make_council(
        [
            Vote.BUY,
            Vote.BUY,
            Vote.SELL,
            Vote.SELL,
            Vote.HOLD,
        ]
    )

    assert council.decision() is None


def test_hold_majority():
    council = make_council(
        [Vote.HOLD] * 3 + [Vote.BUY] * 2
    )

    assert council.decision() == Vote.HOLD


def test_incomplete_council():
    council = FusionCouncil()

    council.submit(make_opinion(AGENTS[0]))

    assert council.decision() is None


def test_duplicate_initial_vote_rejected():
    council = FusionCouncil()

    council.submit(make_opinion(AGENTS[0]))

    with pytest.raises(ValueError):
        council.submit(make_opinion(AGENTS[0]))


def test_revision_requires_all_agents():
    council = FusionCouncil()

    council.submit(make_opinion(AGENTS[0]))

    with pytest.raises(ValueError):
        council.revise(
            make_opinion(AGENTS[0], Vote.SELL)
        )


def test_minority_can_change_majority():
    council = make_council(
        [Vote.BUY] * 3 + [Vote.SELL] * 2
    )

    assert council.decision() == Vote.BUY

    council.revise(
        Opinion(
            agent=AGENTS[0],
            vote=Vote.SELL,
            reasoning="New evidence supports the minority",
            confidence=0.9,
        )
    )

    assert council.decision() == Vote.SELL
    assert len(council.revisions) == 1


def test_original_votes_preserved():
    council = make_council()

    council.revise(
        make_opinion(AGENTS[0], Vote.SELL)
    )

    assert council.initial_opinions[AGENTS[0]].vote == Vote.BUY
    assert council.current_opinions()[AGENTS[0]].vote == Vote.SELL


def test_dissent_preserved():
    council = make_council(
        [Vote.BUY] * 3 + [Vote.SELL] * 2
    )

    dissent = council.dissent()

    assert len(dissent) == 2
    assert all(item.vote == Vote.SELL for item in dissent)


def test_invalid_confidence_rejected():
    with pytest.raises(ValueError):
        make_opinion(AGENTS[0], confidence=1.5)


def test_nan_confidence_rejected():
    with pytest.raises(ValueError):
        make_opinion(AGENTS[0], confidence=float("nan"))


def test_empty_reasoning_rejected():
    with pytest.raises(ValueError):
        Opinion(
            agent=AGENTS[0],
            vote=Vote.BUY,
            reasoning="",
            confidence=0.8,
        )


def test_audit_log():
    council = make_council(
        [Vote.BUY] * 3 + [Vote.SELL] * 2
    )

    log = council.audit_log()

    assert len(log["agents"]) == 5
    assert log["majority_threshold"] == 3
    assert len(log["initial_votes"]) == 5
    assert log["current_decision"] == "BUY"
