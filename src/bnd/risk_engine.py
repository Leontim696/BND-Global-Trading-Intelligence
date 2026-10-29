
"""BND Risk Engine — deterministic paper-trading risk checks."""

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class RiskDecision(str, Enum):
    APPROVE = "APPROVE"
    APPROVE_REDUCED = "APPROVE_REDUCED"
    REJECT = "REJECT"


@dataclass(frozen=True)
class RiskLimits:
    max_risk_per_trade_pct: float
    max_daily_loss_pct: float
    max_drawdown_pct: float
    max_gross_exposure_pct: float
    max_leverage: float

    def __post_init__(self):
        percentages = (
            self.max_risk_per_trade_pct,
            self.max_daily_loss_pct,
            self.max_drawdown_pct,
            self.max_gross_exposure_pct,
        )
        if any(
            not isfinite(value) or value <= 0 or value > 100
            for value in percentages
        ):
            raise ValueError("Risk percentages must be in (0, 100]")
        if not isfinite(self.max_leverage) or self.max_leverage < 1:
            raise ValueError("Maximum leverage must be >= 1")


@dataclass(frozen=True)
class Portfolio:
    equity: float
    daily_loss: float
    drawdown: float
    gross_exposure: float

    def __post_init__(self):
        values = (
            self.equity,
            self.daily_loss,
            self.drawdown,
            self.gross_exposure,
        )
        if any(not isfinite(value) for value in values):
            raise ValueError("Portfolio values must be finite")
        if self.equity <= 0:
            raise ValueError("Portfolio equity must be positive")
        if any(value < 0 for value in values[1:]):
            raise ValueError("Losses and exposure cannot be negative")


@dataclass(frozen=True)
class TradeProposal:
    notional: float
    stop_loss_pct: float
    leverage: float

    def __post_init__(self):
        if not isfinite(self.notional) or self.notional <= 0:
            raise ValueError("Trade notional must be positive")
        if not isfinite(self.stop_loss_pct) or not (
            0 < self.stop_loss_pct <= 100
        ):
            raise ValueError("Stop loss must be in (0, 100]")
        if not isfinite(self.leverage) or self.leverage < 1:
            raise ValueError("Trade leverage must be >= 1")


@dataclass(frozen=True)
class RiskResult:
    decision: RiskDecision
    approved_notional: float
    reason: str


def evaluate_risk(
    portfolio: Portfolio,
    trade: TradeProposal,
    limits: RiskLimits,
) -> RiskResult:
    """Evaluate a proposed virtual trade against configured limits."""

    def reject(reason: str) -> RiskResult:
        return RiskResult(RiskDecision.REJECT, 0.0, reason)

    if trade.leverage > limits.max_leverage:
        return reject("Leverage exceeds configured limit")

    daily_loss_pct = 100 * portfolio.daily_loss / portfolio.equity
    drawdown_pct = 100 * portfolio.drawdown / portfolio.equity

    if daily_loss_pct >= limits.max_daily_loss_pct:
        return reject("Daily loss limit reached")

    if drawdown_pct >= limits.max_drawdown_pct:
        return reject("Drawdown limit reached")

    remaining_exposure = (
        portfolio.equity * limits.max_gross_exposure_pct / 100
        - portfolio.gross_exposure
    )

    remaining_risk = (
        portfolio.equity * limits.max_risk_per_trade_pct / 100
    )

    max_notional_by_risk = (
        remaining_risk / (trade.stop_loss_pct / 100)
    )

    approved = min(
        trade.notional,
        remaining_exposure,
        max_notional_by_risk,
    )

    if approved <= 0:
        return reject("No remaining risk or exposure capacity")

    if approved < trade.notional:
        return RiskResult(
            RiskDecision.APPROVE_REDUCED,
            approved,
            "Position reduced to configured risk limits",
        )

    return RiskResult(
        RiskDecision.APPROVE,
        approved,
        "Trade passes configured preliminary risk checks",
    )
