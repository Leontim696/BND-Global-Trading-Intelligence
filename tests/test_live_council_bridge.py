import os
import unittest
from unittest.mock import patch
from src.bnd.ai_gateway import MockAIProvider
from src.bnd.fusion_council import AGENTS, Vote
from src.bnd.live_council_bridge import run_research_round

class LiveCouncilBridgeTests(unittest.TestCase):
    def test_mock_round_has_five_votes(self):
        providers = {agent: MockAIProvider(agent, Vote.HOLD) for agent in AGENTS}
        with patch.dict(os.environ, {"BND_ALLOW_LIVE_AI": "false"}):
            result = run_research_round("crypto", "BTC", "sample data", providers=providers)
        self.assertEqual(len(result.audit["initial_votes"]), 5)
        self.assertEqual(result.decision, Vote.HOLD)

    def test_live_requires_explicit_approval(self):
        with patch.dict(os.environ, {"BND_ALLOW_LIVE_AI": "false"}):
            with self.assertRaises(RuntimeError):
                run_research_round("crypto", "BTC", "sample", live=True)

    def test_missing_providers_rejected_offline(self):
        with self.assertRaises(RuntimeError):
            run_research_round("crypto", "BTC", "sample")
