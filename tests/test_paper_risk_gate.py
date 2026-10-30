"""Offline regression: mandatory paper-trade risk context must fail closed."""
import unittest

from src.bnd.debate_engine import DebateArgument, DebateEngine, DebateResponse
from src.bnd.fusion_council import AGENTS, FusionCouncil, Opinion, Vote
from src.bnd.risk_engine import Portfolio, RiskLimits, TradeProposal
from src.bnd.trade_coordinator import TradeStatus, coordinate_trade


def unanimous_closed_debate():
    council = FusionCouncil()
    for agent in AGENTS:
        council.submit(Opinion(agent, Vote.BUY, "Independent reasoning", 0.8))
    debate = DebateEngine(council)
    debate.start()
    for agent in AGENTS:
        debate.submit_argument(DebateArgument(agent, "Buy thesis", "Observed volume"))
    for agent in AGENTS:
        debate.submit_response(DebateResponse(agent, "Reviewed evidence", Vote.BUY, 0.8))
    debate.close()
    return debate


class PaperRiskContextTests(unittest.TestCase):
    def setUp(self):
        self.debate = unanimous_closed_debate()
        self.portfolio = Portfolio(10000.0, 0.0, 0.0, 0.0)
        self.limits = RiskLimits(1.0, 3.0, 10.0, 200.0, 3.0)
        self.proposal = TradeProposal(1000.0, 2.0, 1.0)

    def assert_rejected_without_notional(self, outcome):
        self.assertEqual(outcome.status, TradeStatus.REJECTED)
        self.assertIsNone(outcome.direction)
        self.assertEqual(outcome.approved_notional, 0.0)

    def test_missing_limits_reject_even_with_unanimous_buy(self):
        result = coordinate_trade(self.debate, self.portfolio, None, self.proposal)
        self.assert_rejected_without_notional(result)
        self.assertIn("risk limits", result.reason)

    def test_malformed_limits_reject(self):
        result = coordinate_trade(self.debate, self.portfolio, {}, self.proposal)
        self.assert_rejected_without_notional(result)

    def test_missing_portfolio_reject(self):
        result = coordinate_trade(self.debate, None, self.limits, self.proposal)
        self.assert_rejected_without_notional(result)

    def test_malformed_proposal_reject(self):
        result = coordinate_trade(self.debate, self.portfolio, self.limits, {})
        self.assert_rejected_without_notional(result)

    def test_valid_context_still_approves(self):
        result = coordinate_trade(self.debate, self.portfolio, self.limits, self.proposal)
        self.assertEqual(result.status, TradeStatus.APPROVED)
        self.assertEqual(result.direction, "BUY")
        self.assertEqual(result.approved_notional, 1000.0)


if __name__ == "__main__":
    unittest.main()
