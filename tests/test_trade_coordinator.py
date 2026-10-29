
"""Integration tests for BND Trade Coordinator."""

import pytest

from src.bnd.debate_engine import DebateEngine
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


def make_debate(votes, close=True):
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

    debate = DebateEngine(council)
    debate.start()

    if close:
        debate.close()

    return debate


def test_buy_majority_approved(portfolio, limits, proposal):
    debate = make_debate(
        [Vote.BUY] * 4 + [Vote.SELL] * 2
    )

    result = coordinate_trade(
        debate, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.APPROVED
    assert result.direction == "BUY"
    assert result.approved_notional == 2000.0


def test_sell_majority_approved(portfolio, limits, proposal):
    debate = make_debate(
        [Vote.SELL] * 4 + [Vote.BUY] * 2
    )

    result = coordinate_trade(
        debate, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.APPROVED
    assert result.direction == "SELL"


def test_open_debate_blocks_trade(portfolio, limits, proposal):
    debate = make_debate([Vote.BUY] * 6, close=False)

    result = coordinate_trade(
        debate, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.NO_TRADE
    assert result.approved_notional == 0.0
    assert result.direction is None


def test_waiting_debate_blocks_trade(portfolio, limits, proposal):
    council = FusionCouncil()

    for agent in AGENTS:
        council.submit(
            Opinion(
                agent=agent,
                vote=Vote.BUY,
                reasoning="Initial analysis",
                confidence=0.8,
            )
        )

    debate = DebateEngine(council)

    result = coordinate_trade(
        debate, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.NO_TRADE


def test_unanimous_buy_blocked_by_risk(
    portfolio, limits
):
    debate = make_debate([Vote.BUY] * 6)
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


def test_three_three_tie_no_trade(
    portfolio, limits, proposal
):
    debate = make_debate(
        [Vote.BUY] * 3 + [Vote.SELL] * 3
    )

    result = coordinate_trade(
        debate, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.NO_TRADE
    assert result.direction is None


def test_hold_majority_no_trade(
    portfolio, limits, proposal
):
    debate = make_debate(
        [Vote.HOLD] * 4 + [Vote.BUY] * 2
    )

    result = coordinate_trade(
        debate, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.NO_TRADE


def test_missing_proposal_no_trade(portfolio, limits):
    debate = make_debate([Vote.BUY] * 6)

    result = coordinate_trade(
        debate, portfolio, limits, None
    )

    assert result.status == TradeStatus.NO_TRADE


def test_excessive_position_reduced(portfolio, limits):
    debate = make_debate([Vote.BUY] * 6)
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
    debate = make_debate([Vote.BUY] * 6)
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


def test_drawdown_blocks_trade(limits, proposal):
    debate = make_debate([Vote.BUY] * 6)
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


def test_revised_votes_change_direction(
    portfolio, limits, proposal
):
    debate = make_debate(
        [Vote.BUY] * 4 + [Vote.SELL] * 2,
        close=False,
    )

    from src.bnd.debate_engine import DebateArgument

    debate.submit_argument(
        DebateArgument(
            agent=AGENTS[4],
            claim="SELL is supported by new evidence",
            evidence="Liquidity and volatility analysis",
            challenges=(AGENTS[0], AGENTS[1]),
        )
    )

    for agent in AGENTS[:2]:
        debate.revise_vote(
            Opinion(
                agent=agent,
                vote=Vote.SELL,
                reasoning="Persuaded by minority evidence",
                confidence=0.9,
            )
        )

    debate.close()

    result = coordinate_trade(
        debate, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.APPROVED
    assert result.direction == "SELL"
    assert len(debate.council.revisions) == 2


def test_closed_debate_preserves_dissent(
    portfolio, limits, proposal
):
    debate = make_debate(
        [Vote.BUY] * 4 + [Vote.SELL] * 2
    )

    result = coordinate_trade(
        debate, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.APPROVED
    assert len(debate.unresolved_dissent()) == 2
