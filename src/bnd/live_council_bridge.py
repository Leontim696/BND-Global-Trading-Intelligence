"""Explicitly gated bridge from the five provider adapters to Fusion Council.

No requests happen on import or construction. Caller controls each round.
"""
import os
from .ai_gateway import AIRequest
from .fusion_council import AGENTS, Opinion
from .council_orchestrator import run_round
from .multi_ai_providers import configured_adapters


def run_research_round(market, symbol, context, *, live=False, providers=None):
    """Run five independent research opinions; paper research only.

    LIVE requires both a caller opt-in and BND_ALLOW_LIVE_AI=true.
    This function never submits orders. Dissent is retained in audit.
    """
    if live and os.getenv("BND_ALLOW_LIVE_AI", "false").lower() != "true":
        raise RuntimeError("Live research requires explicit environment opt-in")
    if live and os.getenv("BND_LIVE_COUNCIL_APPROVED") != "YES":
        raise RuntimeError("Live council requires explicit paid-round approval")
    if not live and providers is None:
        raise RuntimeError("Offline round requires injected mock providers")
    active = providers if providers is not None else configured_adapters()
    if set(active) != set(AGENTS):
        raise ValueError("Exactly five providers required")
    if not all(isinstance(x, str) and x.strip() for x in (market, symbol, context)):
        raise ValueError("Nonempty research inputs required")
    def analyze(agent):
        response = active[agent].analyze(AIRequest(agent, market, symbol, context))
        if response.agent != agent:
            raise ValueError("Provider agent mismatch")
        return Opinion(response.agent, response.vote, response.reasoning, response.confidence)
    return run_round(analyze)
