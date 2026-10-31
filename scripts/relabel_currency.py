"""Schimbă doar ETICHETA monedei unui cont virtual, fără conversie și fără poziții deschise.

Operațiune unică și auditată (F-08): scrie în jurnalul contului o înregistrare
`currency_relabel` (de la, la, motiv) și, opțional, în jurnalul de audit. Refuză dacă
există poziții deschise sau dacă moneda nu se schimbă. Nu modifică capitalul, ordinele,
limitele sau strategia.

    python scripts/relabel_currency.py --state paper.sqlite --to USD --reason "..." [--audit-log audit.jsonl]
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.bnd import audit_log  # noqa: E402
from src.bnd.paper_engine import PaperEngine, PaperEngineError  # noqa: E402
from src.bnd.reconcile import reconcile  # noqa: E402


def relabel(engine: PaperEngine, new: str, reason: str, now: datetime) -> dict:
    if not re.fullmatch(r"[A-Z]{3}", new):
        raise PaperEngineError("Moneda trebuie să fie un cod de 3 litere mari")
    account = engine.account()
    if account["currency"] == new:
        raise PaperEngineError("Contul are deja această monedă")
    if engine.positions():
        raise PaperEngineError("Contul are poziții deschise: eticheta se schimbă doar pe cont gol")
    if not reason.strip():
        raise PaperEngineError("Motivul e obligatoriu")
    with engine._transaction():
        engine._db.execute("UPDATE account SET currency = ?", (new,))
        engine._log("currency_relabel", {"from": account["currency"], "to": new,
                                         "reason": reason, "capital": account["initial_capital"]},
                    now.isoformat())
    return {"from": account["currency"], "to": new, "capital": account["initial_capital"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="relabel_currency")
    parser.add_argument("--state", required=True)
    parser.add_argument("--to", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--audit-log")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        engine = PaperEngine.open(args.state)
        try:
            result = relabel(engine, args.to, args.reason, now)
            report = reconcile(engine)
        finally:
            engine.close()
    except PaperEngineError as exc:
        print("Error:", exc, file=sys.stderr)
        return 2
    if args.audit_log:
        audit_log.append(args.audit_log, "currency_relabel", {**result, "reason": args.reason,
                                                              "reconciled": report["ok"]}, now)
    print(result, "reconciliat:", report["ok"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
