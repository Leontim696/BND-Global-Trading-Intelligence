"""Safe multi-agent OpenRouter configuration checks (no API calls)."""

import os
from dataclasses import dataclass

from .openrouter_adapter import MODEL_ENV_VARS, OpenRouterAdapter

CLOUD_AGENTS = ("gpt", "claude", "gemini", "deepseek", "grok")


@dataclass(frozen=True)
class AgentReadiness:
    agent: str
    model_configured: bool
    api_key_configured: bool
    live_enabled: bool


def readiness(agent: str) -> AgentReadiness:
    """Report configuration without exposing credentials or making requests."""
    if agent not in CLOUD_AGENTS:
        raise ValueError("Unsupported cloud agent")
    return AgentReadiness(
        agent=agent,
        model_configured=bool(os.getenv(MODEL_ENV_VARS[agent], "").strip()),
        api_key_configured=bool(os.getenv("OPENROUTER_API_KEY", "").strip()),
        live_enabled=os.getenv("BND_ALLOW_LIVE_AI", "false").lower() == "true",
    )


def configured_adapters() -> dict[str, OpenRouterAdapter]:
    """Build independent adapters; live requests require explicit opt-in."""
    enabled = os.getenv("BND_ALLOW_LIVE_AI", "false").lower() == "true"
    return {
        agent: OpenRouterAdapter(agent=agent, allow_live=enabled)
        for agent in CLOUD_AGENTS
    }
