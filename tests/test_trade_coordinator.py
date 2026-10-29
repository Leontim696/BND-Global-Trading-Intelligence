
"""Integration tests for BND Trade Coordinator."""

import pytest

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
    # Test configuration only, not live trading settings.
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


def test_buy_majority_approved(portfolio, limits, proposal):
    council = make_council(
        [Vote.BUY] * 4 + [Vote.SELL] * 2
    )

    result = coordinate_trade(
        council, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.APPROVED
    assert result.direction == "BUY"
    assert result.approved_notional == 2000.0


def test_sell_majority_approved(portfolio, limits, proposal):
    council = make_council(
        [Vote.SELL] * 4 + [Vote.BUY] * 2
    )

    result = coordinate_trade(
        council, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.APPROVED
    assert result.direction == "SELL"


def test_unanimous_buy_blocked_by_risk(
    portfolio, limits
):
    council = make_council([Vote.BUY] * 6)
    dangerous_trade = TradeProposal(
        notional=2000.0,
        stop_loss_pct=2.0,
        leverage=5.0,
    )

    result = coordinate_trade(
        council, portfolio, limits, dangerous_trade
    )

    assert result.status == TradeStatus.REJECTED
    assert result.approved_notional == 0.0


def test_three_three_tie_no_trade(
    portfolio, limits, proposal
):
    council = make_council(
        [Vote.BUY] * 3 + [Vote.SELL] * 3
    )

    result = coordinate_trade(
        council, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.NO_TRADE
    assert result.direction is None
    assert result.approved_notional == 0.0


def test_hold_majority_no_trade(
    portfolio, limits, proposal
):
    council = make_council(
        [Vote.HOLD] * 4 + [Vote.BUY] * 2
    )

    result = coordinate_trade(
        council, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.NO_TRADE
    assert result.approved_notional == 0.0


def test_missing_proposal_no_trade(portfolio, limits):
    council = make_council([Vote.BUY] * 6)

    result = coordinate_trade(
        council, portfolio, limits, None
    )

    assert result.status == TradeStatus.NO_TRADE
    assert result.approved_notional == 0.0


def test_incomplete_council_no_trade(
    portfolio, limits, proposal
):
    council = FusionCouncil()
    council.submit(
        Opinion(
            agent="gpt",
            vote=Vote.BUY,
            reasoning="Market evidence",
            confidence=0.9,
        )
    )

    result = coordinate_trade(
        council, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.NO_TRADE


def test_excessive_position_reduced(portfolio, limits):
    council = make_council([Vote.BUY] * 6)
    large_trade = TradeProposal(
        notional=10000.0,
        stop_loss_pct=5.0,
        leverage=1.0,
    )

    result = coordinate_trade(
        council, portfolio, limits, large_trade
    )

    assert result.status == TradeStatus.REDUCED
    assert result.approved_notional == pytest.approx(2000.0)


def test_daily_loss_blocks_trade(limits, proposal):
    council = make_council([Vote.BUY] * 6)
    losing_portfolio = Portfolio(
        equity=10000.0,
        daily_loss=300.0,
        drawdown=0.0,
        gross_exposure=0.0,
    )

    result = coordinate_trade(
        council, losing_portfolio, limits, proposal
    )

    assert result.status == TradeStatus.REJECTED
    assert result.approved_notional == 0.0


def test_drawdown_blocks_trade(limits, proposal):
    council = make_council([Vote.BUY] * 6)
    losing_portfolio = Portfolio(
        equity=10000.0,
        daily_loss=0.0,
        drawdown=1000.0,
        gross_exposure=0.0,
    )

    result = coordinate_trade(
        council, losing_portfolio, limits, proposal
    )

    assert result.status == TradeStatus.REJECTED
    assert result.approved_notional == 0.0


def test_revised_votes_change_trade_direction(
    portfolio, limits, proposal
):
    council = make_council(
        [Vote.BUY] * 4 + [Vote.SELL] * 2
    )

    council.revise(
        Opinion(
            agent=AGENTS[0],
            vote=Vote.SELL,
            reasoning="New evidence challenges the majority",
            confidence=0.9,
        )
    )
    council.revise(
        Opinion(
            agent=AGENTS[1],
            vote=Vote.SELL,
            reasoning="Minority evidence confirmed",
            confidence=0.9,
        )
    )

    result = coordinate_trade(
        council, portfolio, limits, proposal
    )

    assert result.status == TradeStatus.APPROVED
    assert result.direction == "SELL"

    log = council.audit_log()
    assert len(log["revisions"]) == 2
    assert log["initial_votes"][0]["vote"] == "BUY"
