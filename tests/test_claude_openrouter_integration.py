"""Claude agent integration tests using OpenRouter's mocked HTTP transport.

No API key, network traffic, or paid requests are required.
"""

import json

import pytest

from src.bnd.ai_gateway import AIRequest, ProviderUnavailable
from src.bnd.fusion_council import Vote
from src.bnd.openrouter_adapter import OpenRouterAdapter


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, limit=-1):
        return json.dumps({
            "choices": [{"message": {"content": json.dumps({
                "vote": "HOLD",
                "reasoning": "Insufficient evidence",
                "confidence": 0.65,
            })}}],
            "usage": {"prompt_tokens": 110, "completion_tokens": 24},
        }).encode()[:limit]


def test_claude_uses_configured_model_and_returns_independent_vote(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-test-key")
    monkeypatch.setenv("BND_MODEL_CLAUDE", "anthropic/test-claude")
    calls = []

    def fake_urlopen(request, timeout):
        calls.append({
            "url": request.full_url,
            "authorization": request.get_header("Authorization"),
            "body": json.loads(request.data),
        })
        return FakeResponse()

    monkeypatch.setattr("src.bnd.openrouter_adapter.urlopen", fake_urlopen)
    response = OpenRouterAdapter(agent="claude", allow_live=True).analyze(
        AIRequest(
            agent="claude",
            market="crypto",
            symbol="BTCUSDT",
            context="Simulated price data, no verified edge",
        )
    )

    assert response.agent == "claude"
    assert response.model == "anthropic/test-claude"
    assert response.vote == Vote.HOLD
    assert response.input_tokens == 110
    assert response.output_tokens == 24
    assert len(calls) == 1
    assert calls[0]["url"].startswith("https://")
    assert calls[0]["authorization"] == "Bearer dummy-test-key"
    assert calls[0]["body"]["model"] == "anthropic/test-claude"


def test_claude_is_off_by_default_and_never_sends_request(monkeypatch):
    def forbidden_network(*args, **kwargs):
        pytest.fail("Disabled adapter must never access network")

    monkeypatch.setattr("src.bnd.openrouter_adapter.urlopen", forbidden_network)
    with pytest.raises(ProviderUnavailable, match="disabled"):
        OpenRouterAdapter(agent="claude").analyze(
            AIRequest(
                agent="claude",
                market="forex",
                symbol="EURUSD",
                context="Synthetic data",
            )
        )
