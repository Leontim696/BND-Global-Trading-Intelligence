
"""BND Trade Coordinator — paper-trading decision gateway."""

from dataclasses import dataclass
from enum import Enum

from .fusion_council import FusionCouncil, Vote
from .risk_engine import (
    Portfolio,
    RiskDecision,
    RiskLimits,
    TradeProposal,
    evaluate_risk,
)


class TradeStatus(str, Enum):
    NO_TRADE = "NO_TRADE"
    APPROVED = "APPROVED"
    REDUCED = "REDUCED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class TradeOutcome:
    status: TradeStatus
    direction: str | None
    approved_notional: float
    reason: str


def coordinate_trade(
    council: FusionCouncil,
    portfolio: Portfolio,
    limits: RiskLimits,
    proposal: TradeProposal | None,
) -> TradeOutcome:
    """Evaluate a council decision before any virtual order."""

    decision = council.decision()

    # No majority or incomplete council: no trade.
    if decision is None:
        return TradeOutcome(
            TradeStatus.NO_TRADE,
            None,
            0.0,
            "No valid council majority",
        )

    # HOLD is never an entry signal.
    if decision == Vote.HOLD:
        return TradeOutcome(
            TradeStatus.NO_TRADE,
            None,
            0.0,
            "Council voted HOLD",
        )

    # Missing trade details must never trigger execution.
    if proposal is None:
        return TradeOutcome(
            TradeStatus.NO_TRADE,
            None,
            0.0,
            "Missing trade proposal",
        )

    # Risk Engine has independent veto authority.
    risk = evaluate_risk(portfolio, proposal, limits)

    if risk.decision == RiskDecision.REJECT:
        return TradeOutcome(
            TradeStatus.REJECTED,
            decision.value,
            0.0,
            risk.reason,
        )

    if risk.decision == RiskDecision.APPROVE_REDUCED:
        return TradeOutcome(
            TradeStatus.REDUCED,
            decision.value,
            risk.approved_notional,
            risk.reason,
        )

    return TradeOutcome(
        TradeStatus.APPROVED,
        decision.value,
        risk.approved_notional,
        risk.reason,
    )
