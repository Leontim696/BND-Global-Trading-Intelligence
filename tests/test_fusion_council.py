
"""Unit tests for the BND Fusion Council."""

import pytest

from src.bnd.fusion_council import AGENTS, FusionCouncil, Opinion, Vote


def opinion(agent, vote, reasoning="Evidence-based analysis"):
    return Opinion(
        agent=agent,
        vote=vote,
        reasoning=reasoning,
        confidence=0.8,
    )


def populate(council, votes):
    for agent, vote in zip(AGENTS, votes):
        council.submit(opinion(agent, vote))


def test_all_six_agents_must_vote():
    council = FusionCouncil()
    for agent in AGENTS[:5]:
        council.submit(opinion(agent, Vote.BUY))
    assert council.decision() is None


def test_four_to_two_majority():
    council = FusionCouncil()
    populate(council, [Vote.BUY] * 4 + [Vote.SELL] * 2)
    assert council.decision() == Vote.BUY


def test_three_to_three_has_no_decision():
    council = FusionCouncil()
    populate(council, [Vote.BUY] * 3 + [Vote.SELL] * 3)
    assert council.decision() is None


def test_dissent_is_preserved():
    council = FusionCouncil()
    populate(council, [Vote.BUY] * 4 + [Vote.SELL] * 2)
    dissent = council.dissent()
    assert len(dissent) == 2
    assert all(item.vote == Vote.SELL for item in dissent)


def test_revisions_can_change_majority():
    council = FusionCouncil()
    populate(council, [Vote.BUY] * 4 + [Vote.SELL] * 2)
    assert council.decision() == Vote.BUY

    council.revise(opinion(AGENTS[0], Vote.SELL, "New evidence"))
    council.revise(opinion(AGENTS[1], Vote.SELL, "Minority argument"))

    assert council.decision() == Vote.SELL
    assert len(council.revisions) == 2
    assert council.initial_opinions[AGENTS[0]].vote == Vote.BUY
    assert council.initial_opinions[AGENTS[1]].vote == Vote.BUY


def test_invalid_agent_is_rejected():
    with pytest.raises(ValueError):
        opinion("unknown_agent", Vote.BUY)


def test_invalid_confidence_is_rejected():
    with pytest.raises(ValueError):
        Opinion("gpt", Vote.BUY, "Reasoning", 1.5)


def test_duplicate_initial_vote_is_rejected():
    council = FusionCouncil()
    council.submit(opinion("gpt", Vote.BUY))
    with pytest.raises(ValueError):
        council.submit(opinion("gpt", Vote.SELL))


def test_revision_requires_all_initial_votes():
    council = FusionCouncil()
    council.submit(opinion("gpt", Vote.BUY))
    with pytest.raises(ValueError):
        council.revise(opinion("gpt", Vote.SELL))


def test_audit_log_preserves_vote_history():
    council = FusionCouncil()
    populate(council, [Vote.BUY] * 4 + [Vote.SELL] * 2)
    council.revise(opinion("gpt", Vote.SELL, "New market evidence"))

    log = council.audit_log()
    assert len(log["initial_votes"]) == 6
    assert len(log["revisions"]) == 1
    assert log["initial_votes"][0]["vote"] == "BUY"
    assert log["revisions"][0]["vote"] == "SELL"
