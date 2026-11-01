"""Jurnal de audit cu lanț de hash-uri: o modificare ulterioară se vede.

Fiecare rând (JSON) conține hash-ul rândului dinainte; schimbarea, ștergerea
sau mutarea unui rând strică lanțul, iar ``verify`` spune exact unde. Nu
înlocuiește jurnalul contului virtual: îl completează cu evenimentele
importante (rulări, costuri, opriri).

    python -m src.bnd.audit_log verify audit.jsonl
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:                      # nu există pe Windows; acolo scrierile concurente nu sunt blocate
    import fcntl
except ImportError:       # pragma: no cover
    fcntl = None

GENESIS = "0" * 64


def _digest(previous: str, body: dict) -> str:
    payload = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256((previous + payload).encode("utf-8")).hexdigest()


def _last_valid_hash(text: str) -> str:
    """Hash-ul ultimului rând citibil (un rând rupt de o oprire bruscă se sare)."""
    for line in reversed(text.splitlines()):
        try:
            return json.loads(line)["hash"]
        except (ValueError, KeyError, TypeError):
            continue
    return GENESIS


def append(path, kind: str, data: dict, now: datetime | None = None) -> dict:
    """Adaugă un eveniment; întoarce rândul scris.

    Sigur la rulări simultane (blocare pe fișier), la un rând rupt de o oprire
    bruscă (lanțul continuă de la ultimul rând valid; ``verify`` arată în
    continuare rândul stricat) și scrie durabil (flush + fsync).
    """
    path = Path(path)
    body = {"time": (now or datetime.now(timezone.utc)).isoformat(), "kind": kind,
            "data": data}
    with path.open("a+", encoding="utf-8") as handle:
        if fcntl:
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            handle.seek(0)
            text = handle.read()
            previous = _last_valid_hash(text)
            row = {**body, "previous": previous, "hash": _digest(previous, body)}
            prefix = "" if not text or text.endswith("\n") else "\n"
            handle.write(prefix + json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            if fcntl:
                fcntl.flock(handle, fcntl.LOCK_UN)
    return row


def verify(path, allow_missing: bool = False) -> tuple[bool, str]:
    """(corect, mesaj): primul rând stricat sau lanțul întreg.

    Un jurnal inexistent NU e „corect” (poate fi un istoric pierdut): doar cu ``allow_missing`` (prima rulare)."""
    path = Path(path)
    if not path.exists():
        return (True, "Jurnalul nu există încă.") if allow_missing else (False, "Jurnalul lipsește.")
    number = 0
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
    if number == 0:
        return (True, "Jurnal gol.") if allow_missing else (False, "Jurnalul e gol.")
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
