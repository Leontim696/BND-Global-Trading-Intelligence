
"""BND AI Gateway — provider routing, validation and cost accounting.

MOCK mode is the default. LIVE mode needs all of: BND_ALLOW_LIVE_AI=true,
an unexpired LiveAuthorization with a USD budget, and persistent cost
storage with pricing for every model, so paid calls are always budgeted.

When cost accounting is configured, a budget reservation is created
before provider execution and actual token usage is recorded afterward.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from math import isfinite
from typing import Protocol

from .cost_storage import SQLiteCostStorage
from .cost_tracker import (
    CostTracker,
    money,
    ModelPricing,
    UsageRecord,
)
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
class LiveAuthorization:
    """Owner approval for paid calls: who, how much, until when."""

    approved_by: str
    max_round_usd: Decimal
    expires_at: datetime
    reference: str = ""

    def __post_init__(self):
        if not self.approved_by.strip():
            raise ValueError("approved_by is required")
        object.__setattr__(self, "max_round_usd", money(self.max_round_usd))
        if self.max_round_usd <= 0:
            raise ValueError("A positive USD budget is required")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("Timezone-aware expiry required")

    def check(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        if os.getenv("BND_ALLOW_LIVE_AI", "false").strip().lower() != "true":
            raise ProviderUnavailable("LIVE AI requires BND_ALLOW_LIVE_AI=true")
        if now >= self.expires_at:
            raise ProviderUnavailable("LIVE AI authorisation has expired")


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
    # Upstream provider that served the model, when the router reports it.
    provider: str = ""
    # Cost the router actually billed for this call (USD, as text), when it
    # reports one. It includes hidden thinking tokens that the token counts miss.
    cost_usd: str | None = None

    def reported_cost(self) -> Decimal | None:
        return None if self.cost_usd is None else money(self.cost_usd)

    def __post_init__(self):
        if self.agent not in AGENTS:
            raise InvalidAIResponse("Unknown AI agent")

        if self.cost_usd is not None:
            try:
                money(self.cost_usd)
            except (ValueError, ArithmeticError) as exc:
                raise InvalidAIResponse("Invalid reported cost") from exc

        if not isinstance(self.vote, Vote):
            raise InvalidAIResponse("Invalid vote")

        if not self.reasoning.strip():
            raise InvalidAIResponse("Reasoning is required")

        if (
            not isinstance(self.confidence, (int, float))
            or isinstance(self.confidence, bool)
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
    """Routes requests and optionally accounts for token costs."""

    def __init__(
        self,
        mode: GatewayMode = GatewayMode.MOCK,
        cost_storage: SQLiteCostStorage | None = None,
        pricing: dict[str, ModelPricing] | None = None,
        estimated_input_tokens: int = 1000,
        estimated_output_tokens: int = 1000,
        live_authorization: LiveAuthorization | None = None,
    ):
        if not isinstance(mode, GatewayMode):
            raise ValueError("Invalid gateway mode")

        if mode == GatewayMode.LIVE and (live_authorization is None or cost_storage is None):
            raise ValueError("LIVE mode needs a LiveAuthorization and cost storage")

        for tokens in (
            estimated_input_tokens,
            estimated_output_tokens,
        ):
            if (
                not isinstance(tokens, int)
                or isinstance(tokens, bool)
                or tokens < 0
            ):
                raise ValueError("Invalid estimated token usage")

        self.mode = mode
        self.providers: dict[str, AIProvider] = {}
        self.cost_storage = cost_storage
        self.pricing = dict(pricing or {})
        self.estimated_input_tokens = estimated_input_tokens
        self.estimated_output_tokens = estimated_output_tokens
        self.live_authorization = live_authorization

    def register(self, agent: str, provider: AIProvider) -> None:
        if agent not in AGENTS:
            raise ValueError("Unknown AI agent")

        if agent in self.providers:
            raise ValueError("Provider already registered")

        self.providers[agent] = provider

    def analyze(self, request: AIRequest) -> AIResponse:
        if self.mode == GatewayMode.LIVE:
            self.live_authorization.check()

        provider = self.providers.get(request.agent)

        if provider is None:
            raise ProviderUnavailable(
                f"No provider registered for {request.agent}"
            )

        reservation_id = None
        accounting_started = False

        if self.cost_storage is not None:
            model = self._expected_model(request.agent)
            model_pricing = self.pricing.get(model)

            if model_pricing is None:
                raise GatewayError(
                    f"No pricing configured for model {model}"
                )

            estimated_cost = CostTracker.estimate_cost(
                self.estimated_input_tokens,
                self.estimated_output_tokens,
                model_pricing,
            )

            reservation_id = self.cost_storage.reserve(
                estimated_cost
            )

        try:
            response = provider.analyze(request)

            if not isinstance(response, AIResponse):
                raise InvalidAIResponse(
                    "Provider returned an invalid response type"
                )

            if response.agent != request.agent:
                raise InvalidAIResponse(
                    "Provider response agent mismatch"
                )

            if self.cost_storage is not None:
                actual_cost = response.reported_cost()

                if actual_cost is None:
                    model_pricing = self.pricing.get(response.model)

                    if model_pricing is None:
                        raise GatewayError(
                            "No pricing configured for response model"
                        )

                    actual_cost = CostTracker.estimate_cost(
                        response.input_tokens,
                        response.output_tokens,
                        model_pricing,
                    )

                record = UsageRecord(
                    agent=response.agent,
                    model=response.model,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    cost_usd=actual_cost,
                    timestamp=datetime.now(timezone.utc),
                )

                accounting_started = True
                self.cost_storage.finalize(
                    reservation_id,
                    record,
                )

            return response

        except Exception:
            if (
                reservation_id is not None
                and not accounting_started
            ):
                self.cost_storage.release(reservation_id)
            raise

    def _expected_model(self, agent: str) -> str:
        """Model the agent's provider is configured to call."""
        provider = self.providers.get(agent)
        expected = getattr(provider, "expected_model", None)
        if callable(expected):
            expected = expected()
        return expected or f"mock-{agent}"

    def estimate_cost(self, agent: str) -> Decimal:
        """Worst-case cost of one call, from the configured token estimate."""
        model = self._expected_model(agent)
        pricing = self.pricing.get(model)
        if pricing is None:
            if self.mode == GatewayMode.LIVE:
                raise GatewayError(f"No pricing configured for model {model}")
            return Decimal("0")
        return CostTracker.estimate_cost(
            self.estimated_input_tokens, self.estimated_output_tokens, pricing)

    def actual_cost(self, response: AIResponse) -> Decimal:
        reported = response.reported_cost()
        if reported is not None:
            return reported
        pricing = self.pricing.get(response.model)
        if pricing is None:
            return Decimal("0")
        return CostTracker.estimate_cost(response.input_tokens, response.output_tokens, pricing)

    def registered_agents(self) -> list[str]:
        return [
            agent for agent in AGENTS
            if agent in self.providers
        ]


def create_mock_gateway(
    cost_storage: SQLiteCostStorage | None = None,
    pricing: dict[str, ModelPricing] | None = None,
) -> AIGateway:
    """Create a gateway with all five mock providers."""

    gateway = AIGateway(
        cost_storage=cost_storage,
        pricing=pricing,
    )

    for agent in AGENTS:
        gateway.register(
            agent,
            MockAIProvider(agent=agent),
        )

    return gateway
