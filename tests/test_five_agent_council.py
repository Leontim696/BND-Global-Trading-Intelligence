"""Offline tests; never contact OpenRouter."""
import importlib.util
import os
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "overnight_five_agent_council.py"
spec = importlib.util.spec_from_file_location("five_agent_review", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ReviewSafetyTests(unittest.TestCase):
    def setUp(self):
        self.models = {a: "vendor/model" for a in m.AGENTS}
        self.bodies = {a: b"{}" for a in m.AGENTS}

    def run_fake(self, response, run="0.25", per="0.10"):
        calls = []
        def fake(agent, model, body):
            calls.append(agent)
            return response(agent) if callable(response) else dict(response)
        result = m.process_agents(self.models, self.bodies, fake,
                                  Decimal(run), Decimal(per))
        return result, calls

    def test_default_disabled(self):
        with patch.dict(os.environ, {"BND_ALLOW_PAID_AI": "false"}):
            self.assertFalse(m.enabled())

    def test_invalid_costs(self):
        for x in ("NaN", "Infinity", "-1", "", True, None):
            self.assertIsNone(m.cost(x))

    def test_zero_cost_allowed(self):
        self.assertEqual(m.cost("0"), Decimal("0"))

    def test_invalid_budget(self):
        with patch.dict(os.environ, {"BND_MAX_RUN_COST_USD": "2",
                                     "BND_MAX_CALL_COST_USD": "0.1"}):
            with self.assertRaises(ValueError):
                m.configuration()

    def test_unknown_stops(self):
        result, calls = self.run_fake({"status": "failed", "billing": "unknown"})
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["status"], "halted_billing_unknown")

    def test_http_error_cannot_be_assumed_free(self):
        result, calls = self.run_fake({"status": "failed", "billing": "unknown",
                                       "http_status": 400})
        self.assertEqual(len(calls), 1)
        self.assertFalse(result["cost_reporting_complete"])

    def test_invalid_reported_cost_stops(self):
        result, calls = self.run_fake({"status": "ok", "billing": "reported",
                                       "cost_usd": "NaN"})
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["successful_agents"], 0)

    def test_budget_reservation(self):
        result, calls = self.run_fake({"status": "ok", "billing": "reported",
                                       "cost_usd": "0.10"})
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["status"], "halted_budget")

    def test_per_call_exceeded(self):
        result, calls = self.run_fake({"status": "ok", "billing": "reported",
                                       "cost_usd": "0.11"})
        self.assertEqual(len(calls), 1)
        self.assertTrue(result["call_cap_exceeded"])

    def test_both_budget_limits_exceeded(self):
        result, calls = self.run_fake({"status": "ok", "billing": "reported",
                                       "cost_usd": "0.30"})
        self.assertEqual(len(calls), 1)
        self.assertTrue(result["budget_breach_detected"])
        self.assertTrue(result["call_cap_exceeded"])
        self.assertEqual(result["halt_reason"], "run_budget_exceeded")

    def test_exception_stops(self):
        def fail(*args):
            raise TimeoutError("simulated")
        result, calls = self.run_fake(fail)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["status"], "halted_billing_unknown")

    def test_schema_rejects_missing_evidence(self):
        data = {"choices": [{"finish_reason": "stop", "message": {
            "content": '{"finding":"bug","evidence":null,"risk":"high","suggested_patch":null}'
        }}]}
        with self.assertRaises(ValueError):
            m.proposal(data)

    def test_schema_accepts_no_finding(self):
        data = {"choices": [{"finish_reason": "stop", "message": {
            "content": '{"finding":null,"evidence":null,"risk":"none","suggested_patch":null}'
        }}]}
        self.assertEqual(m.proposal(data)["risk"], "none")

    def test_call_gate_never_sends_when_disabled(self):
        with patch.dict(os.environ, {"BND_ALLOW_PAID_AI": "false"}):
            with patch.object(m, "urlopen", side_effect=AssertionError("network")):
                r = m.call("GPT", "vendor/model", "fake", b"{}")
        self.assertEqual(r["billing"], "not_attempted")

if __name__ == "__main__":
    unittest.main()


class FailureDiagnosticsTests(unittest.TestCase):
    def test_rejected_answer_keeps_reason_and_finish_reason(self):
        import io
        import json

        body = json.dumps({"choices": [{"finish_reason": "length",
                                         "message": {"content": "{\"finding\": null"}}],
                           "usage": {"cost": 0.02}}).encode()

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        with patch.dict(os.environ, {"BND_ALLOW_PAID_AI": "true"}), \
                patch.object(m, "urlopen", lambda *a, **k: Response(body)):
            result = m.call("CLAUDE", "m/x", "key", b"{}")

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["billing"], "reported")
        self.assertEqual(result["cost_usd"], "0.02")
        self.assertEqual(result["finish_reason"], "length")
        self.assertEqual(result["error_detail"], "Incomplete response")


class TargetedRoundTests(unittest.TestCase):
    def test_agent_selection(self):
        self.assertEqual(m.selected_agents(""), m.AGENTS)
        self.assertEqual(m.selected_agents("gemini, claude"), ("CLAUDE", "GEMINI"))
        for bad in ("nobody", "claude,claude", "claude,llama"):
            with self.assertRaises(ValueError):
                m.selected_agents(bad)

    def test_configuration_needs_models_only_for_chosen_agents(self):
        env = {"BND_MODEL_CLAUDE": "anthropic/claude-opus-5.5", "OPENROUTER_API_KEY": "k",
               "BND_MAX_RUN_COST_USD": "0.5", "BND_MAX_CALL_COST_USD": "0.2"}
        with patch.dict(os.environ, env, clear=True):
            models, run, per, _ = m.configuration(("CLAUDE",))
            self.assertEqual(models, {"CLAUDE": "anthropic/claude-opus-5.5"})
            with self.assertRaises(ValueError):
                m.configuration(m.AGENTS)

    def test_only_chosen_agents_are_called(self):
        calls = []

        def fake(agent, model, body):
            calls.append(agent)
            return {"status": "ok", "billing": "reported", "cost_usd": "0.01", "model": model}

        chosen = ("CLAUDE", "GEMINI")
        result = m.process_agents({a: "v/m" for a in chosen}, {a: b"{}" for a in chosen}, fake,
                                  Decimal("0.5"), Decimal("0.2"), chosen)

        self.assertEqual(calls, ["CLAUDE", "GEMINI"])
        self.assertEqual((result["status"], result["total_agents"]), ("ok", 2))

    def test_audit_files_are_checked_and_get_more_text(self):
        files = m.audit_files("src/bnd/paper_engine.py, src/bnd/safety.py")
        self.assertEqual([f.name for f in files], ["paper_engine.py", "safety.py"])
        self.assertIsNone(m.audit_files(""))
        for bad in ("/etc/passwd", "src/../README.md", "src/bnd/missing.py", "README.md",
                    "src/bnd"):
            with self.assertRaises(ValueError):
                m.audit_files(bad)

        included, coverage = m.sources(files[:1])
        self.assertEqual(coverage["included_files"], 1)
        # One file may be read in full (up to 45,000 characters)...
        self.assertEqual(len(included[0]["excerpt"]), min(45000, included[0]["total_chars"]))
        self.assertFalse(included[0]["truncated"])
        # ...two or more share the budget: 29,000 each, here a 42,000-character file is cut.
        big = [Path("src/bnd/paper_engine.py"), Path("src/bnd/safety.py")]
        included, _ = m.sources(big)
        self.assertEqual(len(included[0]["excerpt"]), 29000)
        self.assertTrue(included[0]["truncated"])
