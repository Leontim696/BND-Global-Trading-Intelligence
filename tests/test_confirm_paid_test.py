"""The paid-test confirmation gate tolerates phone keyboards, nothing else."""

import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "confirm_paid_test.py"
spec = importlib.util.spec_from_file_location("confirm_paid_test", SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class GateTests(unittest.TestCase):
    def test_exact_and_phone_variants_pass(self):
        for text in ("RUN-PAID-TEST", "run-paid-test", "Run-Paid-Test", " RUN-PAID-TEST ",
                     "“RUN-PAID-TEST”", "RUN–PAID–TEST", "RUN - PAID - TEST",
                     "`RUN-PAID-TEST`"):
            self.assertTrue(gate.confirmed("workflow_dispatch", text), text)

    def test_anything_else_is_refused(self):
        for text in ("NO", "", "NORUN-PAID-TEST", "RUN-PAID-TESTS", "RUN PAID TEST",
                     "RUNPAIDTEST", "RUN-PAID", "yes"):
            self.assertFalse(gate.confirmed("workflow_dispatch", text), text)
        # A push or a schedule never counts, even with the right words.
        self.assertFalse(gate.confirmed("push", "RUN-PAID-TEST"))
        self.assertFalse(gate.confirmed("schedule", "RUN-PAID-TEST"))

    def test_main_writes_the_sign_and_the_output(self):
        import tempfile

        folder = tempfile.mkdtemp()
        output = Path(folder) / "out.txt"
        cwd = os.getcwd()
        os.chdir(folder)
        try:
            with patch.dict(os.environ, {"EVENT": "workflow_dispatch", "CONFIRMATION": "NO",
                                         "GITHUB_OUTPUT": str(output)}):
                gate.main()
            sign = json.loads((Path(folder) / "overnight-reports" / "gate.json").read_text())
        finally:
            os.chdir(cwd)

        self.assertEqual(output.read_text().strip(), "confirmed=false")
        self.assertEqual(sign["received"], "NO")
        self.assertEqual(sign["received_codepoints"], [78, 79])
