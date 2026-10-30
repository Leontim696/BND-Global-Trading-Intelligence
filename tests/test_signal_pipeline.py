"""End to end: market data -> five agents -> debate -> decision -> virtual
trade -> position closed. Mock agents only; no paid calls, no real orders."""

from datetime import datetime, timedelta, timezone

import pytest

from src.bnd.ai_gateway import AIGateway, AIRequest, MockAIProvider
from src.bnd.debate_engine import DebateArgument, DebateEngine, DebateResponse
from src.bnd.decision_rules import DecisionRule, decide
from src.bnd.fusion_council import AGENTS, FusionCouncil, Vote
from src.bnd.market_data import Candle
from src.bnd.paper_engine import EngineLimits, Instrument, PaperEngine
from src.bnd.signal_pipeline import average_true_range, build_signal, execute_decision, plan_order

T0 = datetime(2026, 2, 2, tzinfo=timezone.utc)
DAY = timedelta(days=1)


def history(count=30):
    candles, price = [], 100.0
    for i in range(count):
        close = price + (1.0 if i % 2 == 0 else -0.5)
        candles.append(Candle(T0 + DAY * i, price, max(price, close) + 0.5,
                              min(price, close) - 0.5, close, 1_000_000))
        price = close
    return candles


def council_from_agents(votes):
    """Independent first opinions from five (mock) providers via the gateway."""
    gateway = AIGateway()
    for agent, (vote, confidence) in zip(AGENTS, votes):
        gateway.register(agent, MockAIProvider(agent=agent, vote=vote, confidence=confidence))
    council = FusionCouncil()
    for agent in AGENTS:
        response = gateway.analyze(AIRequest(agent, "forex", "EURUSD", "Daily candles, trend up"))
        council.submit(response.to_opinion())
    return council


def run_debate(council):
    debate = DebateEngine(council)
    debate.start()
    for agent in AGENTS:
        debate.submit_argument(DebateArgument(agent, "Trend continuation", "Higher highs, rising ATR"))
    for agent, opinion in council.current_opinions().items():
        debate.submit_response(DebateResponse(agent, "Final view", opinion.vote, opinion.confidence))
    debate.close()
    return debate


def votes_of(council):
    return {a: {"vote": o.vote.value, "confidence": o.confidence}
            for a, o in council.current_opinions().items()}


@pytest.fixture
def engine(tmp_path):
    e = PaperEngine.create(tmp_path / "e2e.db", 10_000,
                           limits=EngineLimits(max_risk_per_trade_pct=2.0), now=T0)
    e.register_instrument(Instrument("EURUSD", "forex", fee_pct=0.01, slippage_pct=0.01))
    for candle in history():
        e.on_bar("EURUSD", candle)
    yield e
    e.close()


def test_end_to_end_from_data_to_closed_virtual_position(engine):
    candles = history()
    council = council_from_agents([(Vote.BUY, 0.8)] * 4 + [(Vote.SELL, 0.7)])
    debate = run_debate(council)
    decision = decide(debate.council, DecisionRule.WEIGHTED)
    now = candles[-1].open_time

    record = execute_decision(engine, decision, "EURUSD", candles, "round-1", now,
                              votes_of(debate.council), risk_pct=1.0)

    assert decision.vote == Vote.BUY and record["order"]["status"] == "PENDING"
    signal = record["signal"]
    assert signal["stop_loss"] < signal["entry_price"] < signal["take_profit"]
    # 1% of 10,000 at risk between entry and stop.
    assert record["plan"]["quantity"] * (signal["entry_price"] - signal["stop_loss"]) == pytest.approx(100)
    assert record["plan"]["estimated_round_trip_costs"] > 0

    # Next bar fills at the open; a later rally reaches the take-profit.
    last = candles[-1].close
    engine.on_bar("EURUSD", Candle(now + DAY, last, last + 0.2, last - 0.2, last, 1_000_000))
    assert engine.positions()[0]["quantity"] == pytest.approx(record["plan"]["quantity"])
    target = signal["take_profit"]
    engine.on_bar("EURUSD", Candle(now + 2 * DAY, last, target + 1, last - 0.1, target, 1_000_000))

    assert engine.positions() == []
    assert engine.fills()[-1]["reason"] == "take_profit"
    assert engine.equity() > 10_000
    journal = engine.journal("council_decision")[0]["payload"]
    assert journal["decision"]["dissenting"] == ["deepseek"]
    assert journal["votes"]["deepseek"]["vote"] == "SELL"


def test_hold_decision_journals_but_does_not_trade(engine):
    candles = history()
    council = council_from_agents([(Vote.BUY, 0.6), (Vote.SELL, 0.6), (Vote.HOLD, 0.9),
                                   (Vote.HOLD, 0.9), (Vote.BUY, 0.6)])
    decision = decide(run_debate(council).council, DecisionRule.WEIGHTED)

    record = execute_decision(engine, decision, "EURUSD", candles, "round-2",
                              candles[-1].open_time, votes_of(council))

    assert record["signal"] is None and record["order"] is None
    assert engine.orders() == []
    # Weighted support: HOLD 1.8 of 3.6 = 50% < 60%, so it is uncertain.
    logged = engine.journal("council_decision")[0]["payload"]["decision"]
    assert decision.vote == Vote.HOLD and logged["uncertain"] is True
    assert logged["vote"] == "HOLD"


def test_sizing_shrinks_after_losses(engine):
    candles = history()
    signal = build_signal(decide(council_from_agents([(Vote.BUY, 0.9)] * 5)),
                          "EURUSD", candles, "s", votes_of(council_from_agents([(Vote.BUY, 0.9)] * 5)))
    fresh = plan_order(engine, signal)
    engine._db.execute("UPDATE account SET peak_equity = 12500")   # now 20% below peak

    after_loss = plan_order(engine, signal)

    # Default max drawdown 25%: 20% drawdown leaves 20% of the normal risk.
    assert after_loss["risk_scale"] == pytest.approx(0.2)
    assert after_loss["quantity"] == pytest.approx(fresh["quantity"] * 0.2)


def test_sell_signal_has_stop_above_entry(engine):
    candles = history()
    council = council_from_agents([(Vote.SELL, 0.9)] * 5)
    signal = build_signal(decide(council), "EURUSD", candles, "s", votes_of(council))

    assert signal.direction == "SELL"
    assert signal.take_profit < signal.entry_price < signal.stop_loss


def test_engine_still_rejects_a_council_order(tmp_path):
    e = PaperEngine.create(tmp_path / "rej.db", 10_000, now=T0)
    e.register_instrument(Instrument("EURUSD", "forex"))
    candles = history()
    for candle in candles[:-1]:
        e.on_bar("EURUSD", candle)
    council = council_from_agents([(Vote.BUY, 0.9)] * 5)
    # Data is stale: the last bar was never delivered and time has moved on.
    record = execute_decision(e, decide(council), "EURUSD", candles, "r", T0 + 60 * DAY,
                              votes_of(council))

    assert record["order"]["status"] == "REJECTED" and "Stale" in record["order"]["reason"]
    e.close()


def test_atr_matches_hand_calculation():
    candles = [Candle(T0 + DAY * i, 10, 10 + h, 10 - h, 10, 1) for i, h in enumerate([1, 1, 2, 3])]

    # True ranges 2, 4, 6; period 2: seed (2 + 4) / 2 = 3, then (3 + 6) / 2 = 4.5.
    assert average_true_range(candles, 2) == pytest.approx(4.5)
