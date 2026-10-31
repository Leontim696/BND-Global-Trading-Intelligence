"""Jurnal de audit cu lanț de hash-uri: o modificare ulterioară se vede.

Fiecare rând (JSON) conține hash-ul rândului dinainte; schimbarea, ștergerea
sau mutarea unui rând strică lanțul, iar ``verify`` spune exact unde. Nu
înlocuiește jurnalul contului virtual: îl completează cu evenimentele
importante (rulări, costuri, opriri).

    python -m src.bnd.audit_log verify audit.jsonl
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64


def _digest(previous: str, body: dict) -> str:
    payload = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256((previous + payload).encode("utf-8")).hexdigest()


def append(path, kind: str, data: dict, now: datetime | None = None) -> dict:
    """Adaugă un eveniment; întoarce rândul scris."""
    path = Path(path)
    previous = GENESIS
    if path.exists() and path.stat().st_size:
        previous = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])["hash"]
    body = {"time": (now or datetime.now(timezone.utc)).isoformat(), "kind": kind,
            "data": data}
    row = {**body, "previous": previous, "hash": _digest(previous, body)}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return row


def verify(path) -> tuple[bool, str]:
    """(corect, mesaj): primul rând stricat sau lanțul întreg."""
    path = Path(path)
    if not path.exists():
        return True, "Jurnalul nu există încă."
    previous = GENESIS
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(line)
            body = {"time": row["time"], "kind": row["kind"], "data": row["data"]}
        except (ValueError, KeyError, TypeError):
            return False, f"Rândul {number} nu poate fi citit."
        if row.get("previous") != previous:
            return False, f"Rândul {number}: lanțul e rupt (rând lipsă sau mutat)."
        if row.get("hash") != _digest(previous, body):
            return False, f"Rândul {number}: conținutul a fost modificat."
        previous = row["hash"]
    return True, f"Lanț corect până la rândul {number}."


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or args[0] != "verify":
        print("Folosire: python -m src.bnd.audit_log verify audit.jsonl", file=sys.stderr)
        return 2
    ok, message = verify(args[1])
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
