
"""BND Trade Coordinator — paper-trading decision gateway."""

from dataclasses import dataclass
from enum import Enum

from .debate_engine import DebateEngine, DebateStatus
from .fusion_council import AGENTS, Vote
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
    debate: DebateEngine,
    portfolio: Portfolio,
    limits: RiskLimits,
    proposal: TradeProposal | None,
) -> TradeOutcome:
    """Evaluate a paper trade after debate and risk checks."""

    if debate.status != DebateStatus.CLOSED:
        return TradeOutcome(
            TradeStatus.NO_TRADE,
            None,
            0.0,
            "Debate must be closed before trading",
        )

    council = debate.council

    if len(council.initial_opinions) != len(AGENTS):
        return TradeOutcome(
            TradeStatus.NO_TRADE,
            None,
            0.0,
            "All active agents must submit initial opinions",
        )

    if debate.missing_arguments():
        return TradeOutcome(
            TradeStatus.NO_TRADE,
            None,
            0.0,
            "Missing debate arguments",
        )

    if debate.missing_responses():
        return TradeOutcome(
            TradeStatus.NO_TRADE,
            None,
            0.0,
            "Missing final debate responses",
        )

    decision = council.decision()

    if decision is None:
        return TradeOutcome(
            TradeStatus.NO_TRADE,
            None,
            0.0,
            "No valid council majority",
        )

    if decision == Vote.HOLD:
        return TradeOutcome(
            TradeStatus.NO_TRADE,
            None,
            0.0,
            "Council voted HOLD",
        )

    if proposal is None:
        return TradeOutcome(
            TradeStatus.NO_TRADE,
            None,
            0.0,
            "Missing trade proposal",
        )

    # Fail closed if runtime wiring omits mandatory safety context.
    # Static annotations do not protect callers from None or wrong types.
    if not isinstance(limits, RiskLimits):
        return TradeOutcome(
            TradeStatus.REJECTED,
            None,
            0.0,
            "Missing or invalid mandatory risk limits",
        )

    if not isinstance(portfolio, Portfolio):
        return TradeOutcome(
            TradeStatus.REJECTED,
            None,
            0.0,
            "Missing or invalid portfolio risk state",
        )

    if not isinstance(proposal, TradeProposal):
        return TradeOutcome(
            TradeStatus.REJECTED,
            None,
            0.0,
            "Invalid trade proposal",
        )

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
