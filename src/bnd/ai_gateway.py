
"""BND AI Gateway — provider routing and response validation.

Initial version: supports simulated responses and prepares
the interface for future real API integrations.

No live API requests or trading orders are executed here.
"""

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Protocol

from .fusion_council import AGENTS, Opinion, Vote


class GatewayError(Exception):
    """Base exception for AI Gateway errors."""


class ProviderUnavailable(GatewayError):
    """Raised when a provider cannot be reached."""


class InvalidAIResponse(GatewayError):
    """Raised when an AI response is invalid."""


class GatewayMode(str, Enum):
    MOCK = "MOCK"
    LIVE = "LIVE"


@dataclass(frozen=True)
class AIRequest:
    agent: str
    market: str
    symbol: str
    context: str

    def __post_init__(self):
        if self.agent not in AGENTS:
            raise ValueError("Unknown AI agent")

        if not self.market.strip():
            raise ValueError("Market is required")

        if not self.symbol.strip():
            raise ValueError("Symbol is required")

        if not self.context.strip():
            raise ValueError("Analysis context is required")


@dataclass(frozen=True)
class AIResponse:
    agent: str
    vote: Vote
    reasoning: str
    confidence: float
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    def __post_init__(self):
        if self.agent not in AGENTS:
            raise InvalidAIResponse("Unknown AI agent")

        if not isinstance(self.vote, Vote):
            raise InvalidAIResponse("Invalid vote")

        if not self.reasoning.strip():
            raise InvalidAIResponse("Reasoning is required")

        if (
            not isinstance(self.confidence, (int, float))
            or not isfinite(self.confidence)
            or not 0.0 <= self.confidence <= 1.0
        ):
            raise InvalidAIResponse("Invalid confidence")

        if not self.model.strip():
            raise InvalidAIResponse("Model name is required")

        if (
            not isinstance(self.input_tokens, int)
            or isinstance(self.input_tokens, bool)
            or self.input_tokens < 0
            or not isinstance(self.output_tokens, int)
            or isinstance(self.output_tokens, bool)
            or self.output_tokens < 0
        ):
            raise InvalidAIResponse("Invalid token usage")

    def to_opinion(self) -> Opinion:
        return Opinion(
            agent=self.agent,
            vote=self.vote,
            reasoning=self.reasoning,
            confidence=self.confidence,
        )


class AIProvider(Protocol):
    """Interface implemented by AI provider adapters."""

    def analyze(self, request: AIRequest) -> AIResponse:
        ...


@dataclass
class MockAIProvider:
    """Deterministic provider for development and testing."""

    agent: str
    vote: Vote = Vote.HOLD
    confidence: float = 0.5

    def analyze(self, request: AIRequest) -> AIResponse:
        if request.agent != self.agent:
            raise ProviderUnavailable(
                "Provider does not match requested agent"
            )

        return AIResponse(
            agent=self.agent,
            vote=self.vote,
            reasoning=(
                "Simulated analysis for "
                f"{request.market}:{request.symbol}"
            ),
            confidence=self.confidence,
            model=f"mock-{self.agent}",
            input_tokens=0,
            output_tokens=0,
        )


class AIGateway:
    """Routes analysis requests to registered AI providers."""

    def __init__(self, mode: GatewayMode = GatewayMode.MOCK):
        self.mode = mode
        self.providers: dict[str, AIProvider] = {}

    def register(self, agent: str, provider: AIProvider) -> None:
        if agent not in AGENTS:
            raise ValueError("Unknown AI agent")

        if agent in self.providers:
            raise ValueError("Provider already registered")

        self.providers[agent] = provider

    def analyze(self, request: AIRequest) -> AIResponse:
        if self.mode != GatewayMode.MOCK:
            raise ProviderUnavailable(
                "Live API integrations are not configured yet"
            )

        provider = self.providers.get(request.agent)

        if provider is None:
            raise ProviderUnavailable(
                f"No provider registered for {request.agent}"
            )

        response = provider.analyze(request)

        if not isinstance(response, AIResponse):
            raise InvalidAIResponse(
                "Provider returned an invalid response type"
            )

        if response.agent != request.agent:
            raise InvalidAIResponse(
                "Provider response agent mismatch"
            )

        return response

    def registered_agents(self) -> list[str]:
        return [
            agent for agent in AGENTS
            if agent in self.providers
        ]


def create_mock_gateway() -> AIGateway:
    """Create a gateway with all five mock providers."""

    gateway = AIGateway()

    for agent in AGENTS:
        gateway.register(
            agent,
            MockAIProvider(agent=agent),
        )

    return gateway
