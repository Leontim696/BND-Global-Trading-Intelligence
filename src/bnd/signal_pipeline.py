"""Council decision -> structured signal -> sized order -> paper engine.

Only virtual orders are produced. Every step is written to the engine's
journal: the council's votes and reasons, the signal, the sizing plan
with estimated costs, and the order result, so a decision can be
replayed and audited.

Sizing: risk = equity x risk_pct x (1 - drawdown / max_drawdown), so
exposure shrinks after losses; quantity = risk / |entry - stop|, capped
by the per-instrument position limit. The engine still applies every
mandatory check and may reject the order.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Sequence

from .decision_rules import CouncilDecision
from .fusion_council import Vote
from .market_data import Candle
from .paper_engine import OrderRequest, PaperEngine


@dataclass(frozen=True)
class TradeSignal:
    decision_id: str
    symbol: str
    direction: str          # BUY or SELL
    entry_price: float      # reference: last close; fills happen at the next open
    stop_loss: float
    take_profit: float
    atr: float
    confidence: float
    rule: str
    reasons: tuple


def average_true_range(candles: Sequence[Candle], period: int = 14) -> float:
    """Wilder ATR of the last ``period`` true ranges."""
    if len(candles) < period + 1:
        raise ValueError(f"Need at least {period + 1} candles for ATR")
    ranges = [
        max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
        for p, c in zip(candles, candles[1:])
    ]
    atr = sum(ranges[:period]) / period
    for value in ranges[period:]:
        atr = (atr * (period - 1) + value) / period
    return atr


def build_signal(decision: CouncilDecision, symbol: str, candles: Sequence[Candle],
                 decision_id: str, current_votes: dict, atr_period: int = 14,
                 stop_atr: float = 2.0, reward_risk: float = 2.0) -> TradeSignal | None:
    """A BUY/SELL decision becomes a signal; HOLD or uncertainty gives None."""

    if decision.uncertain or decision.vote == Vote.HOLD:
        return None
    if stop_atr <= 0 or reward_risk <= 0:
        raise ValueError("stop_atr and reward_risk must be positive")
    entry = candles[-1].close
    atr = average_true_range(candles, atr_period)
    if atr <= 0:
        return None
    risk = stop_atr * atr
    long = decision.vote == Vote.BUY
    backers = [v["confidence"] for v in current_votes.values() if v["vote"] == decision.vote.value]
    return TradeSignal(
        decision_id=decision_id,
        symbol=symbol,
        direction=decision.vote.value,
        entry_price=entry,
        stop_loss=entry - risk if long else entry + risk,
        take_profit=entry + reward_risk * risk if long else entry - reward_risk * risk,
        atr=atr,
        confidence=sum(backers) / len(backers) if backers else 0.0,
        rule=decision.rule.value,
        reasons=decision.reasons,
    )


def plan_order(engine: PaperEngine, signal: TradeSignal, risk_pct: float = 1.0) -> dict:
    """Quantity, notional and estimated round-trip costs for a signal."""

    if not 0 < risk_pct <= 10:
        raise ValueError("risk_pct must be in (0, 10]")
    account = engine.account()
    limits = engine.limits()
    instrument = engine.instrument(signal.symbol)
    equity = engine.equity()
    drawdown = max(0.0, account["peak_equity"] - equity) / account["peak_equity"] * 100
    scale = max(0.0, 1 - drawdown / limits.max_drawdown_pct)
    risk_amount = equity * risk_pct / 100 * scale
    per_unit = abs(signal.entry_price - signal.stop_loss)
    quantity = risk_amount / per_unit if per_unit > 0 else 0.0
    cap = equity * limits.max_position_pct / 100 / signal.entry_price
    quantity = min(quantity, cap)
    notional = quantity * signal.entry_price
    cost_rate = 2 * (instrument.fee_pct + instrument.slippage_pct) / 100
    return {
        "equity": equity,
        "drawdown_pct": drawdown,
        "risk_scale": scale,
        "risk_amount": risk_amount,
        "quantity": quantity,
        "notional": notional,
        "estimated_round_trip_costs": notional * cost_rate,
        "capped_by_position_limit": quantity == cap,
    }


def execute_decision(engine: PaperEngine, decision: CouncilDecision, symbol: str,
                     candles: Sequence[Candle], decision_id: str, now: datetime,
                     current_votes: dict, risk_pct: float = 1.0, **signal_options) -> dict:
    """Journal the decision, then submit a sized virtual order if it trades."""

    signal = build_signal(decision, symbol, candles, decision_id, current_votes, **signal_options)
    record = {"decision_id": decision_id, "symbol": symbol, "decision": decision.to_dict(),
              "votes": current_votes, "signal": asdict(signal) if signal else None,
              "plan": None, "order": None}
    if signal is not None:
        plan = plan_order(engine, signal, risk_pct)
        record["plan"] = plan
        if plan["quantity"] > 0:
            order = engine.submit_order(OrderRequest(
                client_order_id=f"{decision_id}:{symbol}",
                symbol=symbol,
                side=signal.direction,
                quantity=plan["quantity"],
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                source=decision_id,
            ), now)
            record["order"] = {"status": order["status"], "reason": order["reason"],
                               "client_order_id": order["client_order_id"]}
    engine.record("council_decision", record, now)
    return record
