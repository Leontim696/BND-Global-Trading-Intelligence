
"""Unit tests for BND Risk Engine."""

import math

import pytest

from src.bnd.risk_engine import (
    Portfolio,
    RiskDecision,
    RiskLimits,
    TradeProposal,
    evaluate_risk,
)


@pytest.fixture
def limits():
    # Test values only; not approved live risk settings.
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


def test_approve_valid_trade(portfolio, limits):
    trade = TradeProposal(2000.0, 2.0, 1.0)
    result = evaluate_risk(portfolio, trade, limits)

    assert result.decision == RiskDecision.APPROVE
    assert result.approved_notional == 2000.0


def test_reduce_excessive_trade_risk(portfolio, limits):
    trade = TradeProposal(10000.0, 5.0, 1.0)
    result = evaluate_risk(portfolio, trade, limits)

    assert result.decision == RiskDecision.APPROVE_REDUCED
    assert result.approved_notional == pytest.approx(2000.0)


def test_reduce_excessive_exposure(limits):
    portfolio = Portfolio(10000.0, 0.0, 0.0, 19000.0)
    trade = TradeProposal(5000.0, 1.0, 1.0)

    result = evaluate_risk(portfolio, trade, limits)

    assert result.decision == RiskDecision.APPROVE_REDUCED
    assert result.approved_notional == pytest.approx(1000.0)


def test_reject_excessive_leverage(portfolio, limits):
    trade = TradeProposal(1000.0, 2.0, 5.0)
    result = evaluate_risk(portfolio, trade, limits)

    assert result.decision == RiskDecision.REJECT
    assert result.approved_notional == 0.0


def test_reject_daily_loss_limit(limits):
    portfolio = Portfolio(10000.0, 300.0, 0.0, 0.0)
    trade = TradeProposal(1000.0, 2.0, 1.0)

    result = evaluate_risk(portfolio, trade, limits)

    assert result.decision == RiskDecision.REJECT


def test_reject_drawdown_limit(limits):
    portfolio = Portfolio(10000.0, 0.0, 1000.0, 0.0)
    trade = TradeProposal(1000.0, 2.0, 1.0)

    result = evaluate_risk(portfolio, trade, limits)

    assert result.decision == RiskDecision.REJECT


def test_reject_when_exposure_full(limits):
    portfolio = Portfolio(10000.0, 0.0, 0.0, 20000.0)
    trade = TradeProposal(1000.0, 2.0, 1.0)

    result = evaluate_risk(portfolio, trade, limits)

    assert result.decision == RiskDecision.REJECT


def test_reduce_to_remaining_daily_loss_capacity(limits):
    # 2.9% already lost today; only 0.1% (USD 10) of risk remains.
    portfolio = Portfolio(10000.0, 290.0, 290.0, 0.0)
    trade = TradeProposal(5000.0, 2.0, 1.0)

    result = evaluate_risk(portfolio, trade, limits)

    assert result.decision == RiskDecision.APPROVE_REDUCED
    assert result.approved_notional == pytest.approx(500.0)


def test_reduce_to_remaining_drawdown_capacity(limits):
    # 9.95% drawdown; only 0.05% (USD 5) of risk remains.
    portfolio = Portfolio(10000.0, 0.0, 995.0, 0.0)
    trade = TradeProposal(5000.0, 2.0, 1.0)

    result = evaluate_risk(portfolio, trade, limits)

    assert result.decision == RiskDecision.APPROVE_REDUCED
    assert result.approved_notional == pytest.approx(250.0)


def test_reject_negative_notional():
    with pytest.raises(ValueError):
        TradeProposal(-100.0, 2.0, 1.0)


def test_reject_zero_equity():
    with pytest.raises(ValueError):
        Portfolio(0.0, 0.0, 0.0, 0.0)


def test_reject_invalid_stop_loss():
    with pytest.raises(ValueError):
        TradeProposal(1000.0, 0.0, 1.0)


def test_reject_nan_leverage():
    with pytest.raises(ValueError):
        TradeProposal(1000.0, 2.0, math.nan)


def test_reject_infinite_equity():
    with pytest.raises(ValueError):
        Portfolio(math.inf, 0.0, 0.0, 0.0)


def test_reject_invalid_risk_limits():
    with pytest.raises(ValueError):
        RiskLimits(0.0, 3.0, 10.0, 200.0, 3.0)


def test_reject_duplicate_or_negative_loss():
    with pytest.raises(ValueError):
        Portfolio(10000.0, -100.0, 0.0, 0.0)
