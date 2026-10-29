
"""Tests for AI Gateway SQLite cost control.

All providers are simulated. No network requests or trading orders.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from bnd.ai_gateway import (
    AIGateway,
    AIRequest,
    AIResponse,
    GatewayError,
    GatewayMode,
    InvalidAIResponse,
    MockAIProvider,
    ProviderUnavailable,
)
from bnd.cost_storage import SQLiteCostStorage
from bnd.cost_tracker import (
    BudgetExceeded,
    BudgetLimits,
    ModelPricing,
)
from bnd.fusion_council import Vote


MODEL = "mock-gpt"
PRICING = ModelPricing(
    input_per_million=Decimal("10"),
    output_per_million=Decimal("20"),
)


def make_storage(tmp_path, daily="1", monthly="10"):
    return SQLiteCostStorage(
        tmp_path / "gateway_costs.sqlite",
        BudgetLimits(
            daily_usd=Decimal(daily),
            monthly_usd=Decimal(monthly),
        ),
    )


def make_request():
    return AIRequest(
        agent="gpt",
        market="crypto",
        symbol="BTC/USDT",
        context="Simulated market research only",
    )


def make_gateway(storage, provider=None):
    gateway = AIGateway(
        mode=GatewayMode.MOCK,
        cost_storage=storage,
        pricing={MODEL: PRICING},
        estimated_input_tokens=1000,
        estimated_output_tokens=1000,
    )
    gateway.register(
        "gpt",
        provider or MockAIProvider(agent="gpt"),
    )
    return gateway


def make_response(input_tokens=1000, output_tokens=1000):
    return AIResponse(
        agent="gpt",
        vote=Vote.HOLD,
        reasoning="Simulated research result",
        confidence=0.5,
        model=MODEL,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


class FixedUsageProvider:
    def __init__(self, response):
        self.response = response

    def analyze(self, request):
        return self.response


class FailingProvider:
    def analyze(self, request):
        raise ProviderUnavailable("Simulated provider failure")


class InvalidProvider:
    def analyze(self, request):
        return {"invalid": "response"}


def test_gateway_records_actual_cost(tmp_path):
    storage = make_storage(tmp_path)
    provider = FixedUsageProvider(make_response())
    gateway = make_gateway(storage, provider)

    response = gateway.analyze(make_request())

    assert response.vote == Vote.HOLD

    summary = storage.summary()

    assert summary["record_count"] == 1
    assert summary["active_reservations"] == 0
    assert summary["daily_committed_usd"] == Decimal("0.03")
    assert summary["by_agent_usd"]["gpt"] == Decimal("0.03")


def test_gateway_rejects_insufficient_budget(tmp_path):
    storage = make_storage(
        tmp_path,
        daily="0.01",
        monthly="0.01",
    )
    gateway = make_gateway(storage)

    with pytest.raises(BudgetExceeded):
        gateway.analyze(make_request())

    summary = storage.summary()

    assert summary["record_count"] == 0
    assert summary["active_reservations"] == 0


def test_gateway_releases_reservation_on_provider_failure(tmp_path):
    storage = make_storage(tmp_path)
    gateway = make_gateway(storage, FailingProvider())

    with pytest.raises(ProviderUnavailable):
        gateway.analyze(make_request())

    summary = storage.summary()

    assert summary["record_count"] == 0
    assert summary["active_reservations"] == 0
    assert summary["daily_committed_usd"] == Decimal("0")


def test_gateway_releases_reservation_on_invalid_response(tmp_path):
    storage = make_storage(tmp_path)
    gateway = make_gateway(storage, InvalidProvider())

    with pytest.raises(InvalidAIResponse):
        gateway.analyze(make_request())

    summary = storage.summary()

    assert summary["record_count"] == 0
    assert summary["active_reservations"] == 0


def test_gateway_persists_actual_over_budget_cost(tmp_path):
    storage = make_storage(
        tmp_path,
        daily="0.05",
        monthly="0.05",
    )

    provider = FixedUsageProvider(
        make_response(
            input_tokens=3000,
            output_tokens=3000,
        )
    )
    gateway = make_gateway(storage, provider)

    with pytest.raises(BudgetExceeded):
        gateway.analyze(make_request())

    reopened = make_storage(
        tmp_path,
        daily="0.05",
        monthly="0.05",
    )
    summary = reopened.summary()

    assert summary["record_count"] == 1
    assert summary["active_reservations"] == 0
    assert summary["daily_committed_usd"] == Decimal("0.09")


def test_gateway_rejects_missing_pricing(tmp_path):
    storage = make_storage(tmp_path)

    gateway = AIGateway(
        cost_storage=storage,
        pricing={},
    )
    gateway.register("gpt", MockAIProvider(agent="gpt"))

    with pytest.raises(GatewayError):
        gateway.analyze(make_request())

    assert storage.summary()["active_reservations"] == 0


def test_gateway_keeps_live_mode_disabled(tmp_path):
    storage = make_storage(tmp_path)
    gateway = AIGateway(
        mode=GatewayMode.LIVE,
        cost_storage=storage,
        pricing={MODEL: PRICING},
    )
    gateway.register("gpt", MockAIProvider(agent="gpt"))

    with pytest.raises(ProviderUnavailable):
        gateway.analyze(make_request())

    assert storage.summary()["record_count"] == 0
    assert storage.summary()["active_reservations"] == 0
