
"""Integration tests for the five-agent BND Trade Coordinator."""

import pytest

from src.bnd.debate_engine import (
    DebateArgument,
    DebateEngine,
    DebateResponse,
    DebateStatus,
)
from src.bnd.fusion_council import (
    AGENTS,
    FusionCouncil,
    Opinion,
    Vote,
)
from src.bnd.risk_engine import (
    Portfolio,
    RiskLimits,
    TradeProposal,
)
from src.bnd.trade_coordinator import (
    TradeStatus,
    coordinate_trade,
)


@pytest.fixture
def limits():
    return RiskLimits(
        max_risk_per_trade_pct=1.0,
        max_daily_loss_pct=3.0,
        max_drawdown_pct=10.0,
        max_gross_exposure_pct=200.0,
        max_leverage=3.0,
    )


@pytest.fixture
def portfolio():
    return Portfolio(
        equity=10000.0,
        daily_loss=0.0,
        drawdown=0.0,
        gross_exposure=0.0,
    )


@pytest.fixture
def proposal():
    return TradeProposal(
        notional=2000.0,
        stop_loss_pct=2.0,
        leverage=1.0,
    )


def make_council(votes):
    assert len(votes) == len(AGENTS)

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


def add_participation(debate, skip_response=None):
    """Register one argument and response per active agent."""

    for agent in AGENTS:
        debate.submit_argument(
            DebateArgument(
                agent=agent,
                claim="Market conditions require evaluation",
                evidence="Liquidity and volatility observations",
            )
        )

    for agent in AGENTS:
        if agent == skip_response:
            continue

        opinion = debate.council.current_opinions()[agent]

        debate.submit_response(
            DebateResponse(
                agent=agent,
                reasoning="Reviewed the arguments",
                vote=opinion.vote,
                confidence=opinion.confidence,
            )
        )


def make_debate(votes, close=True):
    council = make_council(votes)
    debate = DebateEngine(council)
    debate.start()

    if close:
        add_participation(debate)
        debate.close()

    return debate


def test_five_agents():
    assert len(AGENTS) == 5


def test_buy_majority_approved(portfolio, limits, proposal):
    debate = make_debate(
        [Vote.BUY] * 3 + [Vote.SELL] * 2
    )

    result = coordinate_trade(
        debate, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.APPROVED
    assert result.direction == "BUY"
    assert result.approved_notional == 2000.0


def test_sell_majority_approved(portfolio, limits, proposal):
    debate = make_debate(
        [Vote.SELL] * 3 + [Vote.BUY] * 2
    )

    result = coordinate_trade(
        debate, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.APPROVED
    assert result.direction == "SELL"


def test_open_debate_blocks_trade(portfolio, limits, proposal):
    debate = make_debate([Vote.BUY] * 5, close=False)

    result = coordinate_trade(
        debate, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.NO_TRADE
    assert result.direction is None
    assert result.approved_notional == 0.0


def test_waiting_debate_blocks_trade(portfolio, limits, proposal):
    council = make_council([Vote.BUY] * 5)
    debate = DebateEngine(council)

    result = coordinate_trade(
        debate, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.NO_TRADE


def test_missing_response_blocks_close():
    debate = make_debate([Vote.BUY] * 5, close=False)

    add_participation(debate, skip_response=AGENTS[-1])

    with pytest.raises(ValueError, match="Missing responses"):
        debate.close()

    assert debate.status == DebateStatus.OPEN


def test_unanimous_buy_blocked_by_risk(portfolio, limits):
    debate = make_debate([Vote.BUY] * 5)

    dangerous_trade = TradeProposal(
        notional=2000.0,
        stop_loss_pct=2.0,
        leverage=5.0,
    )

    result = coordinate_trade(
        debate, portfolio, limits, dangerous_trade
    )

    assert result.status == TradeStatus.REJECTED
    assert result.approved_notional == 0.0


def test_no_majority_no_trade(portfolio, limits, proposal):
    debate = make_debate(
        [
            Vote.BUY,
            Vote.BUY,
            Vote.SELL,
            Vote.SELL,
            Vote.HOLD,
        ]
    )

    result = coordinate_trade(
        debate, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.NO_TRADE
    assert result.direction is None


def test_hold_majority_no_trade(portfolio, limits, proposal):
    debate = make_debate(
        [Vote.HOLD] * 3 + [Vote.BUY] * 2
    )

    result = coordinate_trade(
        debate, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.NO_TRADE


def test_missing_proposal_no_trade(portfolio, limits):
    debate = make_debate([Vote.BUY] * 5)

    result = coordinate_trade(
        debate, portfolio, limits, None
    )

    assert result.status == TradeStatus.NO_TRADE


def test_excessive_position_reduced(portfolio, limits):
    debate = make_debate([Vote.BUY] * 5)

    large_trade = TradeProposal(
        notional=10000.0,
        stop_loss_pct=5.0,
        leverage=1.0,
    )

    result = coordinate_trade(
        debate, portfolio, limits, large_trade
    )

    assert result.status == TradeStatus.REDUCED
    assert result.approved_notional == pytest.approx(2000.0)


def test_daily_loss_blocks_trade(limits, proposal):
    debate = make_debate([Vote.BUY] * 5)

    losing_portfolio = Portfolio(
        equity=10000.0,
        daily_loss=300.0,
        drawdown=0.0,
        gross_exposure=0.0,
    )

    result = coordinate_trade(
        debate, losing_portfolio, limits, proposal
    )

    assert result.status == TradeStatus.REJECTED
    assert result.approved_notional == 0.0


def test_drawdown_blocks_trade(limits, proposal):
    debate = make_debate([Vote.BUY] * 5)

    losing_portfolio = Portfolio(
        equity=10000.0,
        daily_loss=0.0,
        drawdown=1000.0,
        gross_exposure=0.0,
    )

    result = coordinate_trade(
        debate, losing_portfolio, limits, proposal
    )

    assert result.status == TradeStatus.REJECTED
    assert result.approved_notional == 0.0


def test_minority_changes_trade_direction(
    portfolio, limits, proposal
):
    debate = make_debate(
        [Vote.BUY] * 3 + [Vote.SELL] * 2,
        close=False,
    )

    add_participation(debate)

    debate.revise_vote(
        Opinion(
            agent=AGENTS[0],
            vote=Vote.SELL,
            reasoning="New evidence supports SELL",
            confidence=0.9,
        )
    )

    debate.close()

    result = coordinate_trade(
        debate, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.APPROVED
    assert result.direction == "SELL"
    assert len(debate.council.revisions) == 1
    assert (
        debate.council.initial_opinions[AGENTS[0]].vote
        == Vote.BUY
    )


def test_closed_debate_preserves_dissent(
    portfolio, limits, proposal
):
    debate = make_debate(
        [Vote.BUY] * 3 + [Vote.SELL] * 2
    )

    result = coordinate_trade(
        debate, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.APPROVED
    assert len(debate.unresolved_dissent()) == 2


def test_all_five_agents_participated():
    debate = make_debate([Vote.BUY] * 5)

    assert debate.status == DebateStatus.CLOSED
    assert debate.missing_arguments() == []
    assert debate.missing_responses() == []
    assert len(debate.arguments) == 5
    assert len(debate.responses) == 5
