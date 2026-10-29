import unittest
from src.bnd.fusion_council import AGENTS, Opinion, Vote
from src.bnd.council_orchestrator import run_round

class TestCouncilOrchestrator(unittest.TestCase):
    def test_minority_can_reverse_majority(self):
        original = [Vote.BUY, Vote.BUY, Vote.BUY, Vote.HOLD, Vote.HOLD]
        def initial(agent):
            return Opinion(agent, original[AGENTS.index(agent)], "independent", 0.6)
        def revise(agent, opinion, snapshot):
            self.assertEqual(len(snapshot), 5)
            if opinion.vote == Vote.BUY:
                return Opinion(agent, Vote.HOLD, "persuaded by dissent", 0.8)
        result = run_round(initial, revise)
        self.assertEqual(result.decision, Vote.HOLD)
        self.assertEqual(len(result.audit["initial_votes"]), 5)
        self.assertEqual(len(result.audit["revisions"]), 3)

    def test_invalid_agent_fails(self):
        with self.assertRaises(ValueError):
            run_round(lambda agent: Opinion("gpt", Vote.HOLD, "test", 0.5))

    def test_no_majority(self):
        votes = [Vote.BUY, Vote.BUY, Vote.SELL, Vote.SELL, Vote.HOLD]
        result = run_round(lambda agent: Opinion(agent, votes[AGENTS.index(agent)], "reason", 0.5))
        self.assertIsNone(result.decision)
