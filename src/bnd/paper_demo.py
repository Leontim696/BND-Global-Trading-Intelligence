"""Offline end-to-end paper-trading demo. No API calls, no orders.

Runs five mock agents through the council, a one-round debate,
the risk engine and the trade coordinator, then prints the audit.

    python -m src.bnd.paper_demo
"""

import json

from .ai_gateway import AIRequest, create_mock_gateway
from .debate_engine import DebateArgument, DebateEngine, DebateResponse
from .fusion_council import AGENTS, FusionCouncil
from .risk_engine import Portfolio, RiskLimits, TradeProposal
from .trade_coordinator import coordinate_trade


def run_demo(market: str = "crypto", symbol: str = "BTCUSDT") -> dict:
    gateway = create_mock_gateway()
    council = FusionCouncil()

    for agent in AGENTS:
        response = gateway.analyze(
            AIRequest(
                agent=agent,
                market=market,
                symbol=symbol,
                context="Offline demo context; no market data.",
            )
        )
        council.submit(response.to_opinion())

    debate = DebateEngine(council)
    debate.start()

    for agent in AGENTS:
        debate.submit_argument(
            DebateArgument(
                agent=agent,
                claim="Evidence is insufficient for a directional trade.",
                evidence="Mock analysis only; no market data supplied.",
            )
        )

    for agent, opinion in council.current_opinions().items():
        debate.submit_response(
            DebateResponse(
                agent=agent,
                reasoning=opinion.reasoning,
                vote=opinion.vote,
                confidence=opinion.confidence,
            )
        )

    debate.close()

    outcome = coordinate_trade(
        debate,
        Portfolio(
            equity=10_000.0,
            daily_loss=0.0,
            drawdown=0.0,
            gross_exposure=0.0,
        ),
        RiskLimits(
            max_risk_per_trade_pct=1.0,
            max_daily_loss_pct=3.0,
            max_drawdown_pct=10.0,
            max_gross_exposure_pct=200.0,
            max_leverage=3.0,
        ),
        TradeProposal(notional=2_000.0, stop_loss_pct=2.0, leverage=1.0),
    )

    return {
        "market": market,
        "symbol": symbol,
        "trade": {
            "status": outcome.status.value,
            "direction": outcome.direction,
            "approved_notional": outcome.approved_notional,
            "reason": outcome.reason,
        },
        "debate": debate.audit_log(),
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2))
