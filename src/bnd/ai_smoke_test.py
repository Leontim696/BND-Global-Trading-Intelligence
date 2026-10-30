"""Manual, single-agent live OpenRouter smoke test. No trade execution.

Usage:
  BND_ALLOW_LIVE_AI=true OPENROUTER_API_KEY=... BND_MODEL_CLAUDE=... \
    python -m src.bnd.ai_smoke_test --agent claude --confirm-paid-api-call

Run only in a trusted environment with a configured spending limit.
"""
import argparse
import json
import os

from .ai_gateway import AIRequest, ProviderUnavailable
from .multi_ai_providers import CLOUD_AGENTS, configured_adapters, readiness


def run(agent: str, confirmed: bool) -> dict:
    status = readiness(agent)
    if not confirmed:
        raise ProviderUnavailable("Paid API call requires explicit CLI confirmation")
    if not (status.live_enabled and status.api_key_configured and status.model_configured):
        raise ProviderUnavailable("Live opt-in, API key and agent model are all required")
    request = AIRequest(
        agent=agent,
        market="RESEARCH",
        symbol="SMOKE-TEST",
        context=(
            "Connectivity test only. No market prices or actionable evidence "
            "are supplied. Return HOLD and explain why evidence is insufficient."
        ),
    )
    response = configured_adapters()[agent].analyze(request)
    return {
        "agent": response.agent,
        "model": response.model,
        "vote": response.vote.value,
        "reasoning": response.reasoning,
        "confidence": response.confidence,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", choices=CLOUD_AGENTS, required=True)
    parser.add_argument("--confirm-paid-api-call", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.agent, args.confirm_paid_api_call), indent=2))


if __name__ == "__main__":
    main()
