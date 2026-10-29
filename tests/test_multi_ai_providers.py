import pytest
from src.bnd.multi_ai_providers import CLOUD_AGENTS, configured_adapters, readiness

@pytest.mark.parametrize("agent", CLOUD_AGENTS)
def test_all_agents_disabled_without_opt_in(monkeypatch, agent):
    monkeypatch.delenv("BND_ALLOW_LIVE_AI", raising=False)
    assert configured_adapters()[agent].allow_live is False

@pytest.mark.parametrize("agent", CLOUD_AGENTS)
def test_readiness_never_requires_credentials(monkeypatch, agent):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("BND_ALLOW_LIVE_AI", raising=False)
    status = readiness(agent)
    assert status.agent == agent
    assert not status.api_key_configured
    assert not status.live_enabled

def test_unknown_agent_rejected():
    with pytest.raises(ValueError):
        readiness("unknown")
