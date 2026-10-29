
"""Tests for BND Debate Engine."""

import pytest

from src.bnd.fusion_council import (
    AGENTS,
    FusionCouncil,
    Opinion,
    Vote,
)
from src.bnd.debate_engine import (
    DebateArgument,
    DebateEngine,
    DebateStatus,
)


def make_council(votes=None):
    if votes is None:
        votes = [Vote.BUY] * 4 + [Vote.SELL] * 2

    council = FusionCouncil()

    for agent, vote in zip(AGENTS, votes):
        council.submit(
            Opinion(
                agent=agent,
                vote=vote,
                reasoning="Independent analysis",
                confidence=0.8,
            )
        )

    return council


def make_argument(agent=None):
    return DebateArgument(
        agent=agent or AGENTS[4],
        claim="Market conditions favor SELL",
        evidence="Liquidity and volatility analysis",
        challenges=(AGENTS[0],),
    )


def test_initial_status():
    engine = DebateEngine(make_council())

    assert engine.status == DebateStatus.WAITING
    assert engine.round_number == 0


def test_start_debate():
    engine = DebateEngine(make_council())

    engine.start()

    assert engine.status == DebateStatus.OPEN
    assert engine.round_number == 1


def test_cannot_start_without_six_votes():
    council = FusionCouncil()

    council.submit(
        Opinion(
            agent=AGENTS[0],
            vote=Vote.BUY,
            reasoning="Initial analysis",
            confidence=0.8,
        )
    )

    engine = DebateEngine(council)

    with pytest.raises(ValueError):
        engine.start()


def test_cannot_start_twice():
    engine = DebateEngine(make_council())
    engine.start()

    with pytest.raises(ValueError):
        engine.start()


def test_submit_argument():
    engine = DebateEngine(make_council())
    engine.start()

    engine.submit_argument(make_argument())

    assert len(engine.arguments) == 1
    assert engine.arguments[0].agent == AGENTS[4]


def test_argument_requires_open_debate():
    engine = DebateEngine(make_council())

    with pytest.raises(ValueError):
        engine.submit_argument(make_argument())


def test_invalid_argument_rejected():
    with pytest.raises(ValueError):
        DebateArgument(
            agent="unknown_ai",
            claim="SELL",
            evidence="Some evidence",
        )


def test_empty_evidence_rejected():
    with pytest.raises(ValueError):
        DebateArgument(
            agent=AGENTS[0],
            claim="SELL",
            evidence="",
        )


def test_vote_revision_requires_argument():
    engine = DebateEngine(make_council())
    engine.start()

    with pytest.raises(ValueError):
        engine.revise_vote(
            Opinion(
                agent=AGENTS[0],
                vote=Vote.SELL,
                reasoning="Changed view",
                confidence=0.9,
            )
        )


def test_minority_argument_changes_majority():
    council = make_council()
    engine = DebateEngine(council)
    engine.start()

    assert council.decision() == Vote.BUY

    engine.submit_argument(make_argument())

    for agent in AGENTS[:2]:
        engine.revise_vote(
            Opinion(
                agent=agent,
                vote=Vote.SELL,
                reasoning="Persuaded by minority evidence",
                confidence=0.9,
            )
        )

    assert council.decision() == Vote.SELL
    assert len(council.revisions) == 2


def test_minority_can_remain_unconvinced():
    council = make_council()
    engine = DebateEngine(council)
    engine.start()

    engine.submit_argument(make_argument())

    assert council.decision() == Vote.BUY
    assert len(engine.unresolved_dissent()) == 2
    assert len(council.revisions) == 0


def test_next_round():
    engine = DebateEngine(make_council())
    engine.start()

    engine.next_round()

    assert engine.round_number == 2


def test_maximum_rounds_enforced():
    engine = DebateEngine(
        make_council(),
        max_rounds=2,
    )
    engine.start()
    engine.next_round()

    with pytest.raises(ValueError):
        engine.next_round()


def test_close_debate():
    engine = DebateEngine(make_council())
    engine.start()
    engine.close()

    assert engine.status == DebateStatus.CLOSED

    with pytest.raises(ValueError):
        engine.submit_argument(make_argument())


def test_audit_log_preserves_arguments():
    engine = DebateEngine(make_council())
    engine.start()
    engine.submit_argument(make_argument())

    log = engine.audit_log()

    assert log["status"] == "OPEN"
    assert log["round_number"] == 1
    assert len(log["arguments"]) == 1
    assert log["arguments"][0]["agent"] == AGENTS[4]
    assert "council" in log


def test_invalid_round_limit():
    with pytest.raises(ValueError):
        DebateEngine(make_council(), max_rounds=0)
