import pytest

from src.bnd.ai_gateway import ProviderUnavailable
from src.bnd.ai_smoke_test import run
from src.bnd.multi_ai_providers import CLOUD_AGENTS


@pytest.mark.parametrize("agent", CLOUD_AGENTS)
def test_no_call_without_confirmation(monkeypatch, agent):
    monkeypatch.setenv("BND_ALLOW_LIVE_AI", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy")
    monkeypatch.setenv("BND_MODEL_" + agent.upper(), "dummy-model")
    with pytest.raises(ProviderUnavailable, match="confirmation"):
        run(agent, False)


@pytest.mark.parametrize("agent", CLOUD_AGENTS)
def test_no_call_without_live_opt_in(monkeypatch, agent):
    monkeypatch.delenv("BND_ALLOW_LIVE_AI", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy")
    monkeypatch.setenv("BND_MODEL_" + agent.upper(), "dummy-model")
    with pytest.raises(ProviderUnavailable, match="required"):
        run(agent, True)
