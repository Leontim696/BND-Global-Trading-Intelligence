"""Every BND_* variable a workflow sets must be read by the code.

A flag that nothing reads looks like a safety switch but protects nothing.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_KEY = re.compile(r"^\s*(BND_[A-Z0-9_]+)\s*:", re.MULTILINE)


def code_text() -> str:
    files = list((ROOT / "src").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py"))
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


def test_workflow_flags_are_read_by_code():
    code = code_text()
    unused = sorted({
        f"{workflow.name}: {name}"
        for workflow in (ROOT / ".github" / "workflows").glob("*.yml")
        for name in ENV_KEY.findall(workflow.read_text(encoding="utf-8"))
        if f'"{name}"' not in code and f"'{name}'" not in code
        and f'"{name}' not in code and f"'{name}" not in code
    })

    assert unused == [], "Workflow sets flags no code reads: " + ", ".join(unused)
