import pytest

from src.bnd.ai_gateway import MockAIProvider
from src.bnd.council_round import run_round
from src.bnd.fusion_council import AGENTS, Vote


def test_default_five_agents_hold_without_market_evidence():
    result = run_round("CRYPTO", "BTC/USD", "No price feed")
    assert len(result["initial_votes"]) == 5
    assert result["current_decision"] == "HOLD"
    assert result["trading_enabled"] is False
    assert result["revisions"] == []


def test_dissent_preserved_even_when_majority_buys():
    providers = {
        agent: MockAIProvider(agent=agent, vote=Vote.BUY if i < 3 else Vote.SELL)
        for i, agent in enumerate(AGENTS)
    }
    result = run_round("CRYPTO", "BTC/USD", "Synthetic test", providers)
    assert result["current_decision"] == "BUY"
    assert len(result["dissent"]) == 2
    assert {x["agent"] for x in result["dissent"]} == set(AGENTS[3:])


def test_missing_agent_rejected():
    providers = {agent: MockAIProvider(agent) for agent in AGENTS[:-1]}
    with pytest.raises(ValueError, match="five"):
        run_round("CRYPTO", "BTC/USD", "Test", providers)


def test_empty_context_rejected():
    with pytest.raises(ValueError, match="required"):
        run_round("CRYPTO", "BTC/USD", " ")


def test_provider_identity_mismatch_rejected():
    providers = {agent: MockAIProvider(agent) for agent in AGENTS}
    providers["gpt"] = MockAIProvider("claude")
    with pytest.raises(Exception):
        run_round("CRYPTO", "BTC/USD", "Test", providers)
