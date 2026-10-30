"""Offline regression checks for the paid five-agent review boundary.

These tests use fake callbacks and never access the network.
"""
import importlib.util
import unittest
from decimal import Decimal
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "overnight_five_agent_council.py"
spec = importlib.util.spec_from_file_location("five_agent_regression", SCRIPT)
council = importlib.util.module_from_spec(spec)
spec.loader.exec_module(council)


class FiveAgentRegressionTests(unittest.TestCase):
    def setUp(self):
        self.models = {agent: "vendor/model" for agent in council.AGENTS}
        self.bodies = {agent: b"{}" for agent in council.AGENTS}

    def run_fake(self, callback, run="0.25", per="0.05"):
        calls = []

        def tracked(agent, model, body):
            calls.append(agent)
            return callback(agent, model, body)

        result = council.process_agents(
            self.models, self.bodies, tracked, Decimal(run), Decimal(per)
        )
        return result, calls

    def test_all_five_success_with_reported_costs(self):
        def success(agent, model, body):
            return {"status": "ok", "billing": "reported", "cost_usd": "0.01"}

        result, calls = self.run_fake(success)
        self.assertEqual(calls, list(council.AGENTS))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["successful_agents"], 5)
        self.assertEqual(result["reported_cost_usd"], "0.05")
        self.assertTrue(result["cost_reporting_complete"])

    def test_deepseek_runs_first(self):
        self.assertEqual(council.AGENTS[0], "DEEPSEEK")

    def test_missing_billing_halts_after_first_agent(self):
        result, calls = self.run_fake(
            lambda *args: {"status": "failed", "billing": "unknown"}
        )
        self.assertEqual(calls, ["DEEPSEEK"])
        self.assertEqual(result["status"], "halted_billing_unknown")
        self.assertEqual(result["successful_agents"], 0)
        self.assertFalse(result["cost_reporting_complete"])

    def test_per_call_overage_skips_remaining_agents(self):
        result, calls = self.run_fake(
            lambda *args: {"status": "ok", "billing": "reported", "cost_usd": "0.06"}
        )
        self.assertEqual(calls, ["DEEPSEEK"])
        self.assertEqual(result["status"], "halted_budget")
        self.assertTrue(result["call_cap_exceeded"])

    def test_run_reservation_prevents_unaffordable_fifth_call(self):
        result, calls = self.run_fake(
            lambda *args: {"status": "ok", "billing": "reported", "cost_usd": "0.01"},
            run="0.08", per="0.05",
        )
        self.assertEqual(calls, list(council.AGENTS)[:4])
        self.assertEqual(result["status"], "halted_budget")
        self.assertEqual(result["successful_agents"], 4)


if __name__ == "__main__":
    unittest.main()
