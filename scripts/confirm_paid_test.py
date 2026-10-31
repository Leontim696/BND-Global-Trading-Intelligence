"""Gate for the paid AI test: did the owner type the confirmation phrase?

The phrase is RUN-PAID-TEST. Phone keyboards change case, add spaces or
quotes and turn hyphens into dashes, so those differences are ignored;
any other text (including a leftover "NO" in front) is refused. Only a
manual run counts. Writes overnight-reports/gate.json with what was
received (the typed text only, never a secret) and sets the step output
``confirmed``.
"""
import json
import os
import re
import sys
from pathlib import Path

PHRASE = "RUN-PAID-TEST"
DASHES = "‐‑‒–—―−"
IGNORED = re.compile("[\\s`'\"‘’“”]")


def normalise(text: str) -> str:
    for dash in DASHES:
        text = text.replace(dash, "-")
    return IGNORED.sub("", text).upper()


def confirmed(event: str, text: str) -> bool:
    return event == "workflow_dispatch" and normalise(text) == PHRASE


def main() -> int:
    event = os.getenv("EVENT", "")
    text = os.getenv("CONFIRMATION", "")
    ok = confirmed(event, text)
    out = Path("overnight-reports")
    out.mkdir(parents=True, exist_ok=True)
    (out / "gate.json").write_text(json.dumps({
        "event": event, "confirmed": ok, "received": text[:60],
        "received_codepoints": [ord(c) for c in text[:30]],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
        handle.write(f"confirmed={'true' if ok else 'false'}\n")
    print("confirmed" if ok else "not confirmed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
