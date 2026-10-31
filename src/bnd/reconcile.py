"""Reconcilierea contabilă a unui cont virtual, recalculată independent din jurnal.

Pornește doar de la capitalul inițial, tranzacțiile (fills) și costurile din
jurnal (carry, finanțare), le recalculează și le compară cu ce ține contul:
numerar, poziții, ordine, capital, legătura cu înregistrarea de creare. Orice
diferență peste toleranță e raportată. Doar citire; nu modifică nimic.

    python -m src.bnd.reconcile --state paper.sqlite
"""

import argparse
import json
import sys
from math import isfinite

from .paper_engine import PaperEngine, PaperEngineError

TOLERANCE = 1e-6


def _close(a: float, b: float, scale: float = 1.0) -> bool:
    return abs(a - b) <= TOLERANCE * max(1.0, abs(scale))


def reconcile(engine: PaperEngine) -> dict:
    account = engine.account()
    fills = engine.fills()
    checks = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    initial = account["initial_capital"]
    trade_cash = sum(-f["quantity"] * f["price"] for f in fills)
    fees = sum(f["fee"] for f in fills)
    carry = sum(e["payload"]["amount"] for e in engine.journal("carry"))
    financing = sum(e["payload"]["amount"] for e in engine.journal("financing"))
    expected_cash = initial + trade_cash - fees - carry - financing
    check("numerar = capital + tranzacții − comisioane − carry − finanțare",
          _close(expected_cash, account["cash"], initial),
          f"așteptat {expected_cash:.6f}, în cont {account['cash']:.6f}")

    net: dict = {}
    for fill in fills:
        net[fill["symbol"]] = net.get(fill["symbol"], 0.0) + fill["quantity"]
    held = {p["symbol"]: p["quantity"] for p in engine.positions()}
    wrong = [s for s in set(net) | set(held)
             if not _close(net.get(s, 0.0), held.get(s, 0.0), max(abs(net.get(s, 0.0)), 1.0))]
    check("pozițiile = suma tranzacțiilor pe fiecare piață", not wrong, ", ".join(sorted(wrong)))

    by_order: dict = {}
    for fill in fills:
        if fill["client_order_id"]:
            by_order[fill["client_order_id"]] = by_order.get(fill["client_order_id"], 0.0) + abs(fill["quantity"])
    bad_orders = []
    for order in engine.orders():
        filled = by_order.get(order["client_order_id"], 0.0)
        if not _close(filled, order["filled_quantity"], filled) or filled > order["quantity"] * (1 + 1e-9) + 1e-12:
            bad_orders.append(order["client_order_id"])
    check("fiecare ordin: cantitatea umplută = tranzacțiile lui și nu depășește ordinul",
          not bad_orders, ", ".join(bad_orders[:5]))

    created = engine.journal("account_created")
    check("o singură înregistrare de creare, cu capitalul și moneda contului",
          len(created) == 1 and _close(created[0]["payload"]["capital"], initial, initial)
          and created[0]["payload"]["currency"] == account["currency"])

    ids = [o["client_order_id"] for o in engine.orders()]
    check("fără ordine duplicate", len(ids) == len(set(ids)))
    equity = engine.equity()
    check("capital finit și pozitiv sau oprire de siguranță activă",
          isfinite(equity) and (equity > 0 or bool(account["kill_switch"])), f"{equity:.4f}")

    costs = fees + carry + financing
    profit = equity - initial
    return {"ok": all(c["ok"] for c in checks), "checks": checks,
            "currency": account["currency"], "initial": initial, "equity": equity,
            "net_profit": profit, "costs": {"fees": fees, "carry": carry, "financing": financing,
                                            "total": costs},
            "gross_profit_before_costs": profit + costs, "fills": len(fills)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="reconcile")
    parser.add_argument("--state", required=True)
    args = parser.parse_args(argv)
    try:
        engine = PaperEngine.open(args.state)
    except PaperEngineError as exc:
        print("Error:", exc, file=sys.stderr)
        return 2
    try:
        report = reconcile(engine)
    finally:
        engine.close()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
