
"""Tests for BND AI Gateway."""

import pytest

from src.bnd.ai_gateway import (
    AIGateway,
    AIRequest,
    AIResponse,
    GatewayMode,
    InvalidAIResponse,
    MockAIProvider,
    ProviderUnavailable,
    create_mock_gateway,
)
from src.bnd.fusion_council import AGENTS, Opinion, Vote


def make_request(agent="gpt"):
    return AIRequest(
        agent=agent,
        market="crypto",
        symbol="BTCUSDT",
        context="Market trend and volatility analysis",
    )


def test_five_active_agents():
    assert len(AGENTS) == 5
    assert set(AGENTS) == {
        "gpt",
        "claude",
        "gemini",
        "grok",
        "deepseek",
    }


def test_create_mock_gateway():
    gateway = create_mock_gateway()

    assert gateway.mode == GatewayMode.MOCK
    assert gateway.registered_agents() == list(AGENTS)


@pytest.mark.parametrize("agent", AGENTS)
def test_every_agent_can_analyze(agent):
    gateway = create_mock_gateway()

    response = gateway.analyze(make_request(agent))

    assert isinstance(response, AIResponse)
    assert response.agent == agent
    assert response.vote == Vote.HOLD
    assert response.confidence == 0.5
    assert response.model == f"mock-{agent}"
    assert response.input_tokens == 0
    assert response.output_tokens == 0


def test_mock_provider_buy():
    gateway = AIGateway()
    gateway.register(
        "gpt",
        MockAIProvider(
            agent="gpt",
            vote=Vote.BUY,
            confidence=0.85,
        ),
    )

    response = gateway.analyze(make_request())

    assert response.vote == Vote.BUY
    assert response.confidence == 0.85


def test_mock_provider_sell():
    gateway = AIGateway()
    gateway.register(
        "claude",
        MockAIProvider(
            agent="claude",
            vote=Vote.SELL,
            confidence=0.9,
        ),
    )

    response = gateway.analyze(make_request("claude"))

    assert response.vote == Vote.SELL


def test_response_converts_to_opinion():
    response = AIResponse(
        agent="gpt",
        vote=Vote.BUY,
        reasoning="Bullish market structure",
        confidence=0.8,
        model="mock-gpt",
    )

    opinion = response.to_opinion()

    assert isinstance(opinion, Opinion)
    assert opinion.agent == "gpt"
    assert opinion.vote == Vote.BUY
    assert opinion.reasoning == "Bullish market structure"
    assert opinion.confidence == 0.8


def test_invalid_request_agent():
    with pytest.raises(ValueError, match="Unknown AI agent"):
        make_request("local_ai")


@pytest.mark.parametrize(
    "field",
    ["market", "symbol", "context"],
)
def test_empty_request_fields(field):
    values = {
        "agent": "gpt",
        "market": "crypto",
        "symbol": "BTCUSDT",
        "context": "Analysis",
    }
    values[field] = "   "

    with pytest.raises(ValueError):
        AIRequest(**values)


def test_duplicate_provider_rejected():
    gateway = AIGateway()
    gateway.register("gpt", MockAIProvider("gpt"))

    with pytest.raises(
        ValueError,
        match="Provider already registered",
    ):
        gateway.register("gpt", MockAIProvider("gpt"))


def test_unknown_provider_registration_rejected():
    gateway = AIGateway()

    with pytest.raises(ValueError, match="Unknown AI agent"):
        gateway.register("unknown", MockAIProvider("unknown"))


def test_missing_provider_rejected():
    gateway = AIGateway()

    with pytest.raises(
        ProviderUnavailable,
        match="No provider registered",
    ):
        gateway.analyze(make_request())


def test_provider_agent_mismatch():
    gateway = AIGateway()
    gateway.register("gpt", MockAIProvider("claude"))

    with pytest.raises(
        ProviderUnavailable,
        match="Provider does not match",
    ):
        gateway.analyze(make_request())


def test_live_mode_is_blocked():
    gateway = AIGateway(mode=GatewayMode.LIVE)
    gateway.register("gpt", MockAIProvider("gpt"))

    with pytest.raises(
        ProviderUnavailable,
        match="Live API integrations",
    ):
        gateway.analyze(make_request())


def test_invalid_response_agent():
    with pytest.raises(
        InvalidAIResponse,
        match="Unknown AI agent",
    ):
        AIResponse(
            agent="unknown",
            vote=Vote.BUY,
            reasoning="Analysis",
            confidence=0.8,
            model="test-model",
        )


def test_invalid_response_vote():
    with pytest.raises(
        InvalidAIResponse,
        match="Invalid vote",
    ):
        AIResponse(
            agent="gpt",
            vote="BUY",
            reasoning="Analysis",
            confidence=0.8,
            model="test-model",
        )


def test_empty_reasoning_rejected():
    with pytest.raises(
        InvalidAIResponse,
        match="Reasoning is required",
    ):
        AIResponse(
            agent="gpt",
            vote=Vote.BUY,
            reasoning="   ",
            confidence=0.8,
            model="test-model",
        )


@pytest.mark.parametrize(
    "confidence",
    [-0.1, 1.1, float("nan"), float("inf")],
)
def test_invalid_confidence_rejected(confidence):
    with pytest.raises(
        InvalidAIResponse,
        match="Invalid confidence",
    ):
        AIResponse(
            agent="gpt",
            vote=Vote.BUY,
            reasoning="Analysis",
            confidence=confidence,
            model="test-model",
        )


def test_empty_model_rejected():
    with pytest.raises(
        InvalidAIResponse,
        match="Model name is required",
    ):
        AIResponse(
            agent="gpt",
            vote=Vote.BUY,
            reasoning="Analysis",
            confidence=0.8,
            model="   ",
        )


@pytest.mark.parametrize(
    "tokens",
    [-1, 1.5, True],
)
def test_invalid_input_tokens_rejected(tokens):
    with pytest.raises(
        InvalidAIResponse,
        match="Invalid token usage",
    ):
        AIResponse(
            agent="gpt",
            vote=Vote.BUY,
            reasoning="Analysis",
            confidence=0.8,
            model="test-model",
            input_tokens=tokens,
        )


@pytest.mark.parametrize(
    "tokens",
    [-1, 1.5, True],
)
def test_invalid_output_tokens_rejected(tokens):
    with pytest.raises(
        InvalidAIResponse,
        match="Invalid token usage",
    ):
        AIResponse(
            agent="gpt",
            vote=Vote.BUY,
            reasoning="Analysis",
            confidence=0.8,
            model="test-model",
            output_tokens=tokens,
        )


def test_provider_returns_wrong_type():
    class BrokenProvider:
        def analyze(self, request):
            return {"vote": "BUY"}

    gateway = AIGateway()
    gateway.register("gpt", BrokenProvider())

    with pytest.raises(
        InvalidAIResponse,
        match="invalid response type",
    ):
        gateway.analyze(make_request())


def test_provider_returns_wrong_agent():
    class WrongAgentProvider:
        def analyze(self, request):
            return AIResponse(
                agent="claude",
                vote=Vote.BUY,
                reasoning="Analysis",
                confidence=0.8,
                model="test-model",
            )

    gateway = AIGateway()
    gateway.register("gpt", WrongAgentProvider())

    with pytest.raises(
        InvalidAIResponse,
        match="agent mismatch",
    ):
        gateway.analyze(make_request())


def test_registered_agents_preserve_order():
    gateway = AIGateway()

    gateway.register("deepseek", MockAIProvider("deepseek"))
    gateway.register("gpt", MockAIProvider("gpt"))

    assert gateway.registered_agents() == [
        "gpt",
        "deepseek",
    ]


def test_mock_reasoning_contains_market_and_symbol():
    gateway = create_mock_gateway()

    response = gateway.analyze(make_request())

    assert "crypto" in response.reasoning
    assert "BTCUSDT" in response.reasoning
