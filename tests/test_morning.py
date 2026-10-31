"""Rezumatul de dimineață: conținut, ore în ora Germaniei, trimitere, fără apeluri plătite."""

from datetime import datetime, timedelta, timezone

from src.bnd import morning
from src.bnd.decision_registry import DecisionRegistry
from src.bnd.decision_rules import CouncilDecision, DecisionRule
from src.bnd.fusion_council import FusionCouncil, Opinion, Vote
from src.bnd.market_data import Candle
from src.bnd.paper_engine import Instrument, OrderRequest, PaperEngine

NOW = datetime(2026, 11, 6, 4, 5, tzinfo=timezone.utc)


def account_with_overnight_fill(folder):
    t0 = NOW - timedelta(days=2)
    engine = PaperEngine.create(folder / "paper.sqlite", 10_000.0, currency="USD", now=t0)
    engine.register_instrument(Instrument("AAA", "index", fee_pct=0, slippage_pct=0))
    engine.on_bar("AAA", Candle(NOW - timedelta(days=1, hours=5), 100, 100, 100, 100, 1))
    engine.submit_order(OrderRequest("b", "AAA", "BUY", 10, stop_loss=99), NOW - timedelta(days=1))
    engine.on_bar("AAA", Candle(NOW - timedelta(hours=6), 100, 101, 100, 101, 1))
    engine.close()


def test_summary_has_overnight_events_alerts_and_the_plans_in_german_time(tmp_path):
    account_with_overnight_fill(tmp_path)
    registry = DecisionRegistry(tmp_path / "registry.sqlite")
    council = FusionCouncil()
    for agent, vote in (("gpt", Vote.SELL), ("claude", Vote.SELL), ("gemini", Vote.HOLD),
                        ("grok", Vote.HOLD), ("deepseek", Vote.HOLD)):
        council.submit(Opinion(agent, vote, "x", 0.6))
    registry.record("2026-11-05:BITCOIN", NOW - timedelta(hours=6), "BITCOIN", 70000.0, council,
                    CouncilDecision(Vote.HOLD, DecisionRule.MAJORITY, {}, (), (), True, ()),
                    meta={"trace": {"agents": {"grok": {"status": "failed"}}}})

    result = morning.build(tmp_path, None, None, tmp_path, NOW)

    text = result["message"]
    assert result["title"] == "BND: dimineața, ziua 7/16"
    assert "executat: cumpărat AAA" in text
    assert "BITCOIN vinde (2 net)" in text and "Agenți cu eșecuri: grok" in text
    assert "Planuri azi" in text and "22:40: consiliul AI votează" in text      # 21:40 UTC = 22:40 Berlin
    assert "primești comparația consiliului" in text                              # 6.11
    assert "Alerte:" in text and len(text) < 2900


def test_missing_accounts_do_not_break_the_summary(tmp_path):
    result = morning.build(None, None, None, None, NOW)
    assert "nu există încă" in result["message"] and "nicio rundă încă" in result["message"]


def test_send_uses_the_topic_and_does_nothing_without_it(tmp_path, monkeypatch, capsys):
    sent = []
    monkeypatch.setenv("NTFY_TOPIC", "topic-secret-123")
    assert morning.main(["--send"], sender=lambda *a: sent.append(a)) == 0
    assert len(sent) == 1 and sent[0][1].startswith("BND: dimineața")
    monkeypatch.delenv("NTFY_TOPIC")
    assert morning.main(["--send"], sender=lambda *a: (_ for _ in ()).throw(AssertionError())) == 0


def test_exchange_rate_and_euro_equivalents_are_shown(tmp_path):
    account_with_overnight_fill(tmp_path)
    quotes = {"time": NOW.isoformat(), "quotes": {"EURUSD": [1.12, NOW.isoformat()]}}

    result = morning.build(tmp_path, None, None, None, NOW, quotes=quotes)

    assert "Curs EUR/USD: 1.1200" in result["message"]
    assert "≈ 8" in result["message"] or "≈ 9" in result["message"] or "≈ 10" in result["message"]
    assert "€," in result["message"]


def test_ron_rates_and_lei_equivalents_are_shown_when_available(tmp_path):
    account_with_overnight_fill(tmp_path)
    quotes = {"time": NOW.isoformat(), "quotes": {"EURUSD": [1.12, NOW.isoformat()],
                                                  "EURRON": [4.98, NOW.isoformat()]}}

    text = morning.build(tmp_path, None, None, None, NOW, quotes=quotes)["message"]

    assert "EUR/RON: 4.9800" in text and "USD/RON: 4.4464" in text and "lei," in text


def test_snapshot_includes_the_eur_ron_rate_for_display():
    from src.bnd import quotes_snapshot
    result = quotes_snapshot.snapshot(lambda symbol: (4.98 if symbol == "EURRON=X" else 1.0, NOW))
    assert result["quotes"]["EURRON"][0] == 4.98
