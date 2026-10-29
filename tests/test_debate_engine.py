
"""Tests for BND Debate Engine with five active AI agents."""

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
    DebateResponse,
    DebateStatus,
)


def make_council(votes=None):
    if votes is None:
        votes = [Vote.BUY] * 3 + [Vote.SELL] * 2

    council = FusionCouncil()

    for agent, vote in zip(AGENTS, votes):
        council.submit(
            Opinion(
                agent=agent,
                vote=vote,
                reasoning="Independent market analysis",
                confidence=0.8,
            )
        )

    return council


def make_argument(agent):
    return DebateArgument(
        agent=agent,
        claim="Market analysis requires review",
        evidence="Liquidity and volatility observations",
        challenges=(),
    )


def add_all_arguments(engine):
    for agent in AGENTS:
        engine.submit_argument(make_argument(agent))


def add_all_responses(engine):
    current = engine.council.current_opinions()

    for agent in AGENTS:
        opinion = current[agent]

        engine.submit_response(
            DebateResponse(
                agent=agent,
                reasoning="Reviewed the available arguments",
                vote=opinion.vote,
                confidence=opinion.confidence,
            )
        )


def complete_debate(engine):
    engine.start()
    add_all_arguments(engine)
    add_all_responses(engine)
    engine.close()


def test_five_active_agents():
    assert len(AGENTS) == 5


def test_initial_status():
    engine = DebateEngine(make_council())

    assert engine.status == DebateStatus.WAITING
    assert engine.round_number == 0


def test_start_debate():
    engine = DebateEngine(make_council())
    engine.start()

    assert engine.status == DebateStatus.OPEN
    assert engine.round_number == 1


def test_cannot_start_without_all_votes():
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

    engine.submit_argument(make_argument(AGENTS[0]))

    assert len(engine.arguments) == 1
    assert engine.arguments[0].agent == AGENTS[0]


def test_argument_requires_open_debate():
    engine = DebateEngine(make_council())

    with pytest.raises(ValueError):
        engine.submit_argument(make_argument(AGENTS[0]))


def test_invalid_argument_rejected():
    with pytest.raises(ValueError):
        make_argument("local_ai")


def test_empty_evidence_rejected():
    with pytest.raises(ValueError):
        DebateArgument(
            agent=AGENTS[0],
            claim="Market signal",
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
                reasoning="Changed analysis",
                confidence=0.9,
            )
        )


def test_missing_arguments_blocks_close():
    engine = DebateEngine(make_council())
    engine.start()

    with pytest.raises(ValueError, match="Missing arguments"):
        engine.close()

    assert engine.status == DebateStatus.OPEN


def test_one_missing_argument_blocks_close():
    engine = DebateEngine(make_council())
    engine.start()

    for agent in AGENTS[:-1]:
        engine.submit_argument(make_argument(agent))

    add_all_responses(engine)

    with pytest.raises(ValueError, match="Missing arguments"):
        engine.close()


def test_missing_responses_blocks_close():
    engine = DebateEngine(make_council())
    engine.start()
    add_all_arguments(engine)

    with pytest.raises(ValueError, match="Missing responses"):
        engine.close()


def test_one_missing_response_blocks_close():
    engine = DebateEngine(make_council())
    engine.start()
    add_all_arguments(engine)

    for agent in AGENTS[:-1]:
        engine.submit_response(
            DebateResponse(
                agent=agent,
                reasoning="Reviewed evidence",
                vote=engine.council.current_opinions()[agent].vote,
                confidence=0.8,
            )
        )

    with pytest.raises(ValueError, match="Missing responses"):
        engine.close()


def test_all_agents_can_complete_debate():
    engine = DebateEngine(make_council())

    complete_debate(engine)

    assert engine.status == DebateStatus.CLOSED
    assert engine.missing_arguments() == []
    assert engine.missing_responses() == []


def test_minority_can_change_majority():
    council = make_council()
    engine = DebateEngine(council)
    engine.start()

    assert council.decision() == Vote.BUY

    add_all_arguments(engine)

    engine.submit_response(
        DebateResponse(
            agent=AGENTS[0],
            reasoning="Minority evidence is convincing",
            vote=Vote.SELL,
            confidence=0.9,
        )
    )

    for agent in AGENTS[1:]:
        opinion = council.current_opinions()[agent]
        engine.submit_response(
            DebateResponse(
                agent=agent,
                reasoning="Reviewed arguments independently",
                vote=opinion.vote,
                confidence=opinion.confidence,
            )
        )

    engine.close()

    assert council.decision() == Vote.SELL
    assert len(council.revisions) == 1


def test_minority_remains_recorded():
    engine = DebateEngine(make_council())

    complete_debate(engine)

    assert len(engine.unresolved_dissent()) == 2


def test_next_round():
    engine = DebateEngine(make_council())
    engine.start()
    engine.next_round()

    assert engine.round_number == 2


def test_max_rounds_enforced():
    engine = DebateEngine(make_council(), max_rounds=2)
    engine.start()
    engine.next_round()

    with pytest.raises(ValueError):
        engine.next_round()


def test_closed_debate_rejects_arguments():
    engine = DebateEngine(make_council())
    complete_debate(engine)

    with pytest.raises(ValueError):
        engine.submit_argument(make_argument(AGENTS[0]))


def test_closed_debate_rejects_responses():
    engine = DebateEngine(make_council())
    complete_debate(engine)

    with pytest.raises(ValueError):
        engine.submit_response(
            DebateResponse(
                agent=AGENTS[0],
                reasoning="Late response",
                vote=Vote.BUY,
                confidence=0.8,
            )
        )


def test_audit_log_preserves_participation():
    engine = DebateEngine(make_council())
    complete_debate(engine)

    log = engine.audit_log()

    assert log["status"] == "CLOSED"
    assert len(log["arguments"]) == 5
    assert len(log["responses"]) == 5
    assert log["missing_arguments"] == []
    assert log["missing_responses"] == []
    assert "council" in log


def test_invalid_round_limit():
    with pytest.raises(ValueError):
        DebateEngine(make_council(), max_rounds=0)


def test_invalid_response_confidence():
    with pytest.raises(ValueError):
        DebateResponse(
            agent=AGENTS[0],
            reasoning="Invalid confidence",
            vote=Vote.BUY,
            confidence=1.5,
        )
