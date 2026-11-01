"""Punct de control (checkpoint) pentru contul virtual înainte de publicare.

Se rulează în jobul `step`, DUPĂ pasul zilnic. Contul se publică pe ramură doar dacă:
  * fișierul SQLite se deschide și trece `PRAGMA integrity_check`;
  * contul există și capitalul inițial / data creării sunt neschimbate față de starea restaurată;
  * tabelele de istoric (ordine, execuții, jurnal) nu s-au micșorat față de starea restaurată;
  * lanțul jurnalului de audit e corect, starea veche e prefix al celei noi și s-a adăugat cel puțin
    un rând `daily_run` cu aceeași valoare a contului ca în `last_run.json`.
La succes scrie `VALID.json` cu hash-urile fișierelor; jobul de publicare (fără cod de proiect)
verifică hash-urile cu `scripts/verify_marker.sh`. Nu modifică niciun fișier de cont.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import audit_log

FILES = ("paper.sqlite", "audit.jsonl", "last_run.json")
REQUIRED_TABLES = ("account", "orders", "fills", "journal", "positions")
COUNT_QUERIES = {
    "orders": "SELECT COUNT(*) FROM orders",
    "fills": "SELECT COUNT(*) FROM fills",
    "journal": "SELECT COUNT(*) FROM journal",
}


def sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _open_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)


def _snapshot(path: Path) -> dict:
    """Citește din SQLite: integritate, tabele, cont, numărul de rânduri din istoric."""
    out: dict = {"problems": []}
    try:
        db = _open_readonly(path)
    except sqlite3.Error as exc:
        out["problems"].append(f"{path.name}: nu se poate deschide ({exc}).")
        return out
    try:
        try:
            result = [r[0] for r in db.execute("PRAGMA integrity_check")]
        except sqlite3.Error as exc:
            out["problems"].append(f"{path.name}: integrity_check a eșuat ({exc}).")
            return out
        if result != ["ok"]:
            out["problems"].append(f"{path.name}: integrity_check = {result[:3]}.")
            return out
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = [t for t in REQUIRED_TABLES if t not in tables]
        if missing:
            out["problems"].append(f"{path.name}: lipsesc tabelele {missing}.")
            return out
        row = db.execute("SELECT initial_capital, created_at, cash, kill_switch FROM account WHERE id=1").fetchone()
        if row is None:
            out["problems"].append(f"{path.name}: nu există rândul contului.")
            return out
        out["capital"], out["created_at"], out["cash"], out["kill"] = row
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (out["capital"], out["cash"])):
            out["problems"].append(f"{path.name}: capital/cash nefinite.")
        out["counts"] = {name: db.execute(query).fetchone()[0] for name, query in COUNT_QUERIES.items()}
    except sqlite3.Error as exc:
        out["problems"].append(f"{path.name}: eroare SQLite ({exc}).")
    finally:
        db.close()
    return out


def _audit_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def check(state: Path, previous: Path | None = None, new_account: bool = False) -> list[str]:
    """Lista problemelor; goală = starea poate fi publicată."""
    problems: list[str] = []
    for name in FILES:
        if not (state / name).is_file() or (state / name).stat().st_size == 0:
            problems.append(f"{name}: lipsește sau e gol.")
    if problems:
        return problems
    now = _snapshot(state / "paper.sqlite")
    problems += now["problems"]
    ok, message = audit_log.verify(state / "audit.jsonl")
    if not ok:
        problems.append("audit.jsonl: " + message)
    try:
        last = json.loads((state / "last_run.json").read_text(encoding="utf-8"))
        equity = float(last["equity"])
        if not math.isfinite(equity) or equity <= 0:
            problems.append("last_run.json: valoarea contului nu e validă.")
    except (ValueError, KeyError, TypeError):
        problems.append("last_run.json: nu poate fi citit sau nu are `equity`.")
        last, equity = None, None
    lines = _audit_lines(state / "audit.jsonl")
    if lines and equity is not None:
        try:
            tail = json.loads(lines[-1])
            if tail.get("kind") != "daily_run":
                problems.append("audit.jsonl: ultimul rând nu e un `daily_run` (rularea nu s-a încheiat).")
            elif abs(float(tail["data"]["equity"]) - equity) > 0.01:
                problems.append("audit.jsonl și last_run.json au valori diferite ale contului.")
        except (ValueError, KeyError, TypeError):
            problems.append("audit.jsonl: ultimul rând nu poate fi citit.")
    if previous is not None and not new_account:
        before = _snapshot(previous / "paper.sqlite") if (previous / "paper.sqlite").is_file() else None
        if before is None:
            problems.append("starea restaurată lipsește: nu pot compara.")
        elif not before["problems"] and not now["problems"]:
            if before["capital"] != now["capital"] or before["created_at"] != now["created_at"]:
                problems.append("capitalul inițial sau data creării s-au schimbat (cont înlocuit?).")
            for table, count in before["counts"].items():
                if now["counts"][table] < count:
                    problems.append(f"tabelul {table} s-a micșorat ({count} -> {now['counts'][table]}).")
        old_lines = _audit_lines(previous / "audit.jsonl")
        if lines[:len(old_lines)] != old_lines:
            problems.append("audit.jsonl nou nu continuă jurnalul restaurat (istoric rescris).")
        elif len(lines) <= len(old_lines):
            problems.append("audit.jsonl nu are niciun rând nou: pasul zilnic nu s-a încheiat.")
    return problems


def write_marker(state: Path, run_id: str = "") -> Path:
    marker = {"time": datetime.now(timezone.utc).isoformat(), "run_id": run_id,
              "files": {name: sha256(state / name) for name in FILES}}
    path = state / "VALID.json"
    path.write_text(json.dumps(marker, indent=2), encoding="utf-8")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True)
    parser.add_argument("--previous", help="folderul cu starea restaurată înainte de pasul zilnic")
    parser.add_argument("--new", action="store_true", help="cont nou (nu există stare anterioară)")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)
    state = Path(args.state)
    (state / "VALID.json").unlink(missing_ok=True)
    problems = check(state, Path(args.previous) if args.previous else None, args.new)
    if problems:
        for p in problems:
            print("::error::Punct de control respins: " + p)
        return 1
    print("Punct de control valid:", write_marker(state, args.run_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
