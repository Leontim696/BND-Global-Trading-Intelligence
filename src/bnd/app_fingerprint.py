"""Amprenta datelor aplicației de pe telefon: se reîmprospătează doar când s-a schimbat ceva.

Tipărește un hash scurt din ce contează pentru ce arată aplicația: baza contului unic (se schimbă doar când
rulează pasul zilnic), registrul și costurile consiliului, soldul real al cheii (rotunjit la cent), rulările
eșuate recente, alertele și, doar dacă există poziții deschise (valoarea lor depinde de prețuri), cursurile de acum.
Un puls de siguranță (implicit 12 ore) face ca aplicația să nu pară înghețată.

    python -m src.bnd.app_fingerprint --unic U/paper.sqlite --council D4 --balance balance.json \
        --runs runs.json --alerts alerts.json --quotes quotes.json [--last-time ISO --heartbeat-hours 12]
"""

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

IMPORTANT_FAILURES_LOOKBACK = 12


def _bytes_hash(path) -> str:
    path = Path(path) if path else None
    return hashlib.sha256(path.read_bytes()).hexdigest() if path and path.exists() else "-"


def _json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")) if path and Path(path).exists() else None
    except (OSError, ValueError):
        return None


def has_positions(unic_db) -> bool:
    path = Path(unic_db) if unic_db else None
    if not path or not path.exists():
        return False
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return db.execute("SELECT COUNT(*) FROM positions").fetchone()[0] > 0
        finally:
            db.close()
    except sqlite3.Error:
        return True              # nu putem spune: mai bine reîmprospătăm


def fingerprint(unic=None, council=None, balance=None, runs=None, alerts=None, quotes=None) -> str:
    parts = ["unic:" + _bytes_hash(unic)]
    folder = Path(council) if council else None
    for name in ("registry.sqlite", "costs.sqlite"):
        parts.append(f"{name}:" + _bytes_hash(folder / name if folder else None))
    data = _json(balance) or {}
    remaining = data.get("effective_remaining", data.get("key_remaining"))
    parts.append("sold:" + (f"{remaining:.2f}" if isinstance(remaining, (int, float)) else "-"))
    failed = sorted({(r.get("workflowName"), r.get("conclusion"))
                     for r in (_json(runs) or [])[:IMPORTANT_FAILURES_LOOKBACK]
                     if r.get("conclusion") not in (None, "", "success", "skipped", "cancelled")})
    parts.append("esecuri:" + json.dumps(failed, sort_keys=True))
    alert_data = _json(alerts)
    parts.append("alerte:" + json.dumps(alert_data, sort_keys=True, default=str)[:2000] if alert_data else "alerte:-")
    if has_positions(unic):
        parts.append("cursuri:" + _bytes_hash(quotes))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


def needs_refresh(current: str, previous: str | None, last_time: str | None, now: datetime,
                  heartbeat_hours: float = 12) -> tuple[bool, str]:
    if not previous:
        return True, "prima publicare"
    if current != previous:
        return True, "s-au schimbat datele"
    try:
        last = datetime.fromisoformat(last_time) if last_time else None
    except ValueError:
        last = None
    if last is None or now - last >= timedelta(hours=heartbeat_hours):
        return True, f"puls de siguranță (>{heartbeat_hours:g} h)"
    return False, "nimic nou"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="app_fingerprint")
    for name in ("unic", "council", "balance", "runs", "alerts", "quotes"):
        parser.add_argument(f"--{name}")
    parser.add_argument("--previous", help="amprenta publicată ultima dată")
    parser.add_argument("--last-time", help="momentul ultimei publicări (ISO, UTC)")
    parser.add_argument("--heartbeat-hours", type=float, default=12)
    args = parser.parse_args(argv)
    current = fingerprint(args.unic, args.council, args.balance, args.runs, args.alerts, args.quotes)
    refresh, reason = needs_refresh(current, args.previous, args.last_time, datetime.now(timezone.utc),
                                    args.heartbeat_hours)
    print(json.dumps({"fingerprint": current, "refresh": refresh, "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
