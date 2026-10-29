"""Run one independent, auditable five-agent research round.

Default uses mock providers. Live adapters are intentionally not wired here:
the gateway must enforce provider-side spending limits before live council use.
"""
import argparse
import json

from .ai_gateway import AIRequest, AIProvider, MockAIProvider
from .fusion_council import AGENTS, FusionCouncil, Vote


def run_round(market: str, symbol: str, context: str,
              providers: dict[str, AIProvider] | None = None) -> dict:
    """Collect independent votes, then publish majority and dissent."""
    if not market.strip() or not symbol.strip() or not context.strip():
        raise ValueError("Market, symbol and context are required")
    if providers is None:
        providers = {agent: MockAIProvider(agent=agent) for agent in AGENTS}
    if set(providers) != set(AGENTS):
        raise ValueError("Exactly the five council agents are required")
    council = FusionCouncil()
    models = {}
    for agent in AGENTS:
        response = providers[agent].analyze(
            AIRequest(agent=agent, market=market, symbol=symbol, context=context)
        )
        if response.agent != agent:
            raise ValueError("Provider returned another agent's response")
        council.submit(response.to_opinion())
        models[agent] = response.model
    audit = council.audit_log()
    audit.update({
        "market": market,
        "symbol": symbol,
        "models": models,
        "dissent": [
            {"agent": o.agent, "vote": o.vote.value, "reasoning": o.reasoning}
            for o in council.dissent()
        ],
        "execution_mode": "provider_injected" if providers is not None
        else "mock",
        "trading_enabled": False,
    })
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", default="CRYPTO")
    parser.add_argument("--symbol", default="BTC/USD")
    parser.add_argument("--context", default="No verified market data; HOLD.")
    args = parser.parse_args()
    print(json.dumps(run_round(args.market, args.symbol, args.context), indent=2))


if __name__ == "__main__":
    main()
