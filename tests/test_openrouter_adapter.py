
"""Tests for the OpenRouter adapter.

All HTTP requests are simulated. No external API calls.
"""

import json
import socket
from urllib.error import HTTPError, URLError

import pytest

from src.bnd.ai_gateway import (
    AIRequest,
    InvalidAIResponse,
    ProviderUnavailable,
)
from src.bnd.fusion_council import AGENTS, Vote
from src.bnd.openrouter_adapter import (
    MODEL_ENV_VARS,
    OPENROUTER_URL,
    OpenRouterAdapter,
)


def make_request(agent="gpt"):
    return AIRequest(
        agent=agent,
        market="crypto",
        symbol="BTCUSDT",
        context="Market data for independent analysis",
    )


def make_payload(
    vote="BUY",
    reasoning="Positive momentum",
    confidence=0.8,
    prompt_tokens=100,
    completion_tokens=40,
):
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "vote": vote,
                            "reasoning": reasoning,
                            "confidence": confidence,
                        }
                    )
                }
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
    }


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self, size=-1):
        return self.payload[:size]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def mock_http(monkeypatch, payload):
    def fake_urlopen(request, timeout):
        return FakeHTTPResponse(
            json.dumps(payload).encode("utf-8")
        )

    monkeypatch.setattr(
        "src.bnd.openrouter_adapter.urlopen",
        fake_urlopen,
    )


def configure(monkeypatch, agent="gpt"):
    monkeypatch.setenv(
        "OPENROUTER_API_KEY",
        "fake-test-key",
    )
    monkeypatch.setenv(
        MODEL_ENV_VARS[agent],
        "test/model",
    )


def test_five_model_environment_variables():
    assert set(MODEL_ENV_VARS) == set(AGENTS)


def test_openrouter_url_uses_https():
    assert OPENROUTER_URL.startswith("https://")


def test_live_disabled_by_default():
    adapter = OpenRouterAdapter(
        agent="gpt",
        model="test/model",
    )

    with pytest.raises(
        ProviderUnavailable,
        match="disabled",
    ):
        adapter.analyze(make_request())


def test_live_disabled_never_calls_network(monkeypatch):
    def forbidden_urlopen(*args, **kwargs):
        pytest.fail("Network must not be called")

    monkeypatch.setattr(
        "src.bnd.openrouter_adapter.urlopen",
        forbidden_urlopen,
    )

    adapter = OpenRouterAdapter(
        agent="gpt",
        model="test/model",
    )

    with pytest.raises(ProviderUnavailable):
        adapter.analyze(make_request())


def test_unknown_agent_rejected():
    with pytest.raises(ValueError, match="Unknown AI agent"):
        OpenRouterAdapter(agent="local_ai")


@pytest.mark.parametrize(
    "timeout",
    [0, -1, 121, "30"],
)
def test_invalid_timeout_rejected(timeout):
    with pytest.raises(ValueError):
        OpenRouterAdapter(
            agent="gpt",
            timeout=timeout,
        )


def test_agent_mismatch_rejected():
    adapter = OpenRouterAdapter(
        agent="gpt",
        model="test/model",
        allow_live=True,
    )

    with pytest.raises(
        ProviderUnavailable,
        match="does not match",
    ):
        adapter.analyze(make_request("claude"))


def test_missing_model_rejected(monkeypatch):
    monkeypatch.delenv("BND_MODEL_GPT", raising=False)
    monkeypatch.setenv(
        "OPENROUTER_API_KEY",
        "fake-test-key",
    )

    adapter = OpenRouterAdapter(
        agent="gpt",
        allow_live=True,
    )

    with pytest.raises(
        ProviderUnavailable,
        match="No model configured",
    ):
        adapter.analyze(make_request())


def test_missing_api_key_rejected(monkeypatch):
    monkeypatch.delenv(
        "OPENROUTER_API_KEY",
        raising=False,
    )

    adapter = OpenRouterAdapter(
        agent="gpt",
        model="test/model",
        allow_live=True,
    )

    with pytest.raises(
        ProviderUnavailable,
        match="OPENROUTER_API_KEY",
    ):
        adapter.analyze(make_request())


@pytest.mark.parametrize("agent", AGENTS)
def test_each_agent_accepts_valid_response(
    monkeypatch, agent
):
    configure(monkeypatch, agent)
    mock_http(monkeypatch, make_payload())

    adapter = OpenRouterAdapter(
        agent=agent,
        allow_live=True,
    )

    response = adapter.analyze(make_request(agent))

    assert response.agent == agent
    assert response.vote == Vote.BUY
    assert response.confidence == 0.8
    assert response.model == "test/model"
    assert response.input_tokens == 100
    assert response.output_tokens == 40


def test_request_payload_and_authentication(monkeypatch):
    configure(monkeypatch)

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["authorization"] = request.get_header(
            "Authorization"
        )
        captured["timeout"] = timeout
        captured["body"] = json.loads(
            request.data.decode("utf-8")
        )

        return FakeHTTPResponse(
            json.dumps(make_payload()).encode("utf-8")
        )

    monkeypatch.setattr(
        "src.bnd.openrouter_adapter.urlopen",
        fake_urlopen,
    )

    adapter = OpenRouterAdapter(
        agent="gpt",
        allow_live=True,
        timeout=12,
    )

    adapter.analyze(make_request())

    assert captured["url"] == OPENROUTER_URL
    assert captured["method"] == "POST"
    assert captured["authorization"] == "Bearer fake-test-key"
    assert captured["timeout"] == 12
    assert captured["body"]["model"] == "test/model"
    assert captured["body"]["temperature"] == 0
    assert len(captured["body"]["messages"]) == 2
    assert "BTCUSDT" in captured["body"]["messages"][1]["content"]


@pytest.mark.parametrize(
    "vote",
    ["BUY", "SELL", "HOLD"],
)
def test_all_valid_votes(monkeypatch, vote):
    configure(monkeypatch)
    mock_http(
        monkeypatch,
        make_payload(vote=vote),
    )

    response = OpenRouterAdapter(
        agent="gpt",
        allow_live=True,
    ).analyze(make_request())

    assert response.vote == Vote(vote)


def test_http_error_rejected(monkeypatch):
    configure(monkeypatch)

    def fake_urlopen(request, timeout):
        raise HTTPError(
            OPENROUTER_URL,
            429,
            "Too Many Requests",
            {},
            None,
        )

    monkeypatch.setattr(
        "src.bnd.openrouter_adapter.urlopen",
        fake_urlopen,
    )

    with pytest.raises(
        ProviderUnavailable,
        match="429",
    ):
        OpenRouterAdapter(
            agent="gpt",
            allow_live=True,
        ).analyze(make_request())


def test_network_error_rejected(monkeypatch):
    configure(monkeypatch)

    def fake_urlopen(request, timeout):
        raise URLError("Connection failed")

    monkeypatch.setattr(
        "src.bnd.openrouter_adapter.urlopen",
        fake_urlopen,
    )

    with pytest.raises(
        ProviderUnavailable,
        match="network request failed",
    ):
        OpenRouterAdapter(
            agent="gpt",
            allow_live=True,
        ).analyze(make_request())


def test_timeout_rejected(monkeypatch):
    configure(monkeypatch)

    def fake_urlopen(request, timeout):
        raise socket.timeout("Timed out")

    monkeypatch.setattr(
        "src.bnd.openrouter_adapter.urlopen",
        fake_urlopen,
    )

    with pytest.raises(
        ProviderUnavailable,
        match="network request failed",
    ):
        OpenRouterAdapter(
            agent="gpt",
            allow_live=True,
        ).analyze(make_request())


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{}]},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": "not-json"}}]},
        {"choices": [{"message": {"content": "[]"}}]},
    ],
)
def test_malformed_provider_payload_rejected(
    monkeypatch, payload
):
    configure(monkeypatch)
    mock_http(monkeypatch, payload)

    with pytest.raises(InvalidAIResponse):
        OpenRouterAdapter(
            agent="gpt",
            allow_live=True,
        ).analyze(make_request())


@pytest.mark.parametrize(
    "analysis",
    [
        {"vote": "BUY", "reasoning": "OK"},
        {
            "vote": "WAIT",
            "reasoning": "OK",
            "confidence": 0.8,
        },
        {
            "vote": "BUY",
            "reasoning": "",
            "confidence": 0.8,
        },
        {
            "vote": "BUY",
            "reasoning": "OK",
            "confidence": 1.5,
        },
        {
            "vote": "BUY",
            "reasoning": "OK",
            "confidence": 0.8,
            "extra": "unexpected",
        },
    ],
)
def test_invalid_analysis_rejected(
    monkeypatch, analysis
):
    configure(monkeypatch)

    mock_http(
        monkeypatch,
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(analysis)
                    }
                }
            ]
        },
    )

    with pytest.raises(InvalidAIResponse):
        OpenRouterAdapter(
            agent="gpt",
            allow_live=True,
        ).analyze(make_request())


@pytest.mark.parametrize(
    "usage",
    [
        {"prompt_tokens": -1, "completion_tokens": 5},
        {"prompt_tokens": 5, "completion_tokens": -1},
        {"prompt_tokens": 1.5, "completion_tokens": 5},
        {"prompt_tokens": True, "completion_tokens": 5},
        "invalid",
    ],
)
def test_invalid_usage_rejected(monkeypatch, usage):
    configure(monkeypatch)

    payload = make_payload()
    payload["usage"] = usage
    mock_http(monkeypatch, payload)

    with pytest.raises(InvalidAIResponse):
        OpenRouterAdapter(
            agent="gpt",
            allow_live=True,
        ).analyze(make_request())


def test_oversized_response_rejected(monkeypatch):
    configure(monkeypatch)

    def fake_urlopen(request, timeout):
        return FakeHTTPResponse(b"x" * 1_000_001)

    monkeypatch.setattr(
        "src.bnd.openrouter_adapter.urlopen",
        fake_urlopen,
    )

    with pytest.raises(
        InvalidAIResponse,
        match="size limit",
    ):
        OpenRouterAdapter(
            agent="gpt",
            allow_live=True,
        ).analyze(make_request())


def test_missing_usage_defaults_to_zero(monkeypatch):
    configure(monkeypatch)

    payload = make_payload()
    del payload["usage"]
    mock_http(monkeypatch, payload)

    response = OpenRouterAdapter(
        agent="gpt",
        allow_live=True,
    ).analyze(make_request())

    assert response.input_tokens == 0
    assert response.output_tokens == 0


def test_explicit_model_overrides_environment(monkeypatch):
    configure(monkeypatch)
    mock_http(monkeypatch, make_payload())

    adapter = OpenRouterAdapter(
        agent="gpt",
        model="custom/model",
        allow_live=True,
    )

    response = adapter.analyze(make_request())

    assert response.model == "custom/model"


def test_actual_routed_model_is_reported(monkeypatch):
    configure(monkeypatch)
    payload = make_payload()
    payload["model"] = "fallback/actual-model"
    mock_http(monkeypatch, payload)

    response = OpenRouterAdapter(
        agent="gpt",
        allow_live=True,
    ).analyze(make_request())

    assert response.model == "fallback/actual-model"


@pytest.mark.parametrize("model", ["", None, 42])
def test_invalid_routed_model_is_rejected(monkeypatch, model):
    configure(monkeypatch)
    payload = make_payload()
    payload["model"] = model
    mock_http(monkeypatch, payload)

    with pytest.raises(InvalidAIResponse):
        OpenRouterAdapter(
            agent="gpt",
            allow_live=True,
        ).analyze(make_request())


@pytest.mark.parametrize(
    "content",
    [
        '```json\n{"vote": "BUY", "reasoning": "OK", "confidence": 0.7}\n```',
        '```\n{"vote": "BUY", "reasoning": "OK", "confidence": 0.7}\n```',
    ],
)
def test_fenced_json_analysis_accepted(monkeypatch, content):
    configure(monkeypatch)

    mock_http(
        monkeypatch,
        {"choices": [{"message": {"content": content}}]},
    )

    response = OpenRouterAdapter(
        agent="gpt",
        allow_live=True,
    ).analyze(make_request())

    assert response.vote == Vote.BUY
    assert response.confidence == 0.7


def test_malformed_fence_rejected(monkeypatch):
    configure(monkeypatch)

    mock_http(
        monkeypatch,
        {
            "choices": [
                {
                    "message": {
                        "content": '```json\n{"vote": "BUY"}'
                    }
                }
            ]
        },
    )

    with pytest.raises(InvalidAIResponse):
        OpenRouterAdapter(
            agent="gpt",
            allow_live=True,
        ).analyze(make_request())


def test_boolean_confidence_rejected(monkeypatch):
    configure(monkeypatch)

    mock_http(
        monkeypatch,
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "vote": "BUY",
                                "reasoning": "OK",
                                "confidence": True,
                            }
                        )
                    }
                }
            ]
        },
    )

    with pytest.raises(InvalidAIResponse):
        OpenRouterAdapter(
            agent="gpt",
            allow_live=True,
        ).analyze(make_request())


def test_empty_claude_content_has_specific_error(monkeypatch):
    configure(monkeypatch, "claude")
    mock_http(monkeypatch, {
        "choices": [{"message": {"content": "  "}}],
    })

    with pytest.raises(
        InvalidAIResponse,
        match="empty message content",
    ):
        OpenRouterAdapter(
            agent="claude",
            allow_live=True,
        ).analyze(make_request("claude"))


def test_nonempty_invalid_json_remains_rejected(monkeypatch):
    configure(monkeypatch, "claude")
    mock_http(monkeypatch, {
        "choices": [{"message": {"content": "not-json"}}],
    })

    with pytest.raises(
        InvalidAIResponse,
        match="invalid AI response",
    ):
        OpenRouterAdapter(
            agent="claude",
            allow_live=True,
        ).analyze(make_request("claude"))


def test_request_asks_for_short_thinking_and_more_output_when_configured(monkeypatch):
    import io
    import json

    from src.bnd import openrouter_adapter as adapter
    from src.bnd.ai_gateway import AIRequest

    seen = {}

    class Reply(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout):
        seen["payload"] = json.loads(request.data)
        seen["timeout"] = timeout
        body = {"model": "m/x", "choices": [{"message": {"content": json.dumps(
            {"vote": "BUY", "reasoning": "motiv", "confidence": 0.7})}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
        return Reply(json.dumps(body).encode())

    monkeypatch.setattr(adapter, "urlopen", fake_urlopen)
    monkeypatch.setenv("OPENROUTER_API_KEY", "cheie-de-test")

    plain = adapter.OpenRouterAdapter("claude", model="m/x", allow_live=True)
    tuned = adapter.OpenRouterAdapter("claude", model="m/x", allow_live=True, timeout=100,
                                      max_tokens=4000, reasoning_effort="low")
    request = AIRequest("claude", "forex", "EURUSD", "context")

    plain.analyze(request)
    assert seen["payload"]["max_tokens"] == adapter.MAX_OUTPUT_TOKENS
    assert "reasoning" not in seen["payload"]

    answer = tuned.analyze(request)
    assert seen["payload"]["max_tokens"] == 4000 and seen["timeout"] == 100
    assert seen["payload"]["reasoning"] == {"effort": "low", "exclude": True}
    assert answer.vote.value == "BUY" and answer.input_tokens == 100

    for bad in (dict(max_tokens=10), dict(max_tokens=True), dict(reasoning_effort="max")):
        with pytest.raises(ValueError):
            adapter.OpenRouterAdapter("claude", model="m/x", **bad)


def _reply_with_usage(monkeypatch, usage):
    import io
    import json

    from src.bnd import openrouter_adapter as adapter
    from src.bnd.ai_gateway import AIRequest

    class Reply(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    body = {"model": "m/x", "choices": [{"message": {"content": json.dumps(
        {"vote": "SELL", "reasoning": "motiv", "confidence": 0.6})}}], "usage": usage}
    monkeypatch.setattr(adapter, "urlopen", lambda request, timeout: Reply(json.dumps(body).encode()))
    monkeypatch.setenv("OPENROUTER_API_KEY", "cheie-de-test")
    return adapter.OpenRouterAdapter("gpt", model="m/x", allow_live=True).analyze(
        AIRequest("gpt", "forex", "EURUSD", "context"))


def test_the_billed_cost_is_kept_and_a_bad_cost_does_not_reject_the_answer(monkeypatch):
    from decimal import Decimal

    good = _reply_with_usage(monkeypatch, {"prompt_tokens": 10, "completion_tokens": 5,
                                           "cost": 0.0415})
    assert good.cost_usd == "0.0415" and good.reported_cost() == Decimal("0.0415")

    for bad in ("abc", -1, True, None, [1]):
        answer = _reply_with_usage(monkeypatch, {"prompt_tokens": 10, "completion_tokens": 5,
                                                 "cost": bad})
        assert answer.cost_usd is None and answer.vote.value == "SELL"
