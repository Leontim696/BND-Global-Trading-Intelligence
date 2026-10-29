"""Verify overnight diagnostics do not report success when pytest fails."""
import os
from pathlib import Path
import subprocess
import textwrap


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/bnd-overnight-diagnostics.yml"


def _capture_script():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    step = workflow.split("      - name: Capture offline test results\n", 1)[1]
    step = step.split("      - name: Collect code backlog\n", 1)[0]
    return textwrap.dedent(step.split("        run: |\n", 1)[1])


def _run_capture(tmp_path, pytest_exit):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python"
    fake_python.write_text(f"#!/bin/sh\nexit {pytest_exit}\n", encoding="utf-8")
    fake_python.chmod(0o755)
    env = dict(os.environ, PATH=str(fake_bin) + os.pathsep + os.environ["PATH"])
    return subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", _capture_script()],
        cwd=tmp_path, env=env, capture_output=True, text=True, check=False,
    )


def test_diagnostics_failure_is_visible_and_artifact_preserved(tmp_path):
    result = _run_capture(tmp_path, pytest_exit=7)
    assert result.returncode != 0
    assert (tmp_path / "overnight-reports/tests.txt").exists()
    assert "Offline tests failed" in (tmp_path / "overnight-reports/status.txt").read_text()


def test_diagnostics_success_is_not_falsely_failed(tmp_path):
    result = _run_capture(tmp_path, pytest_exit=0)
    assert result.returncode == 0
    assert (tmp_path / "overnight-reports/tests.txt").exists()
    assert not (tmp_path / "overnight-reports/status.txt").exists()
