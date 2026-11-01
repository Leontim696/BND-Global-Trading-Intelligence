"""Alerte Smart-Money (doar text, o singură dată fiecare): ce merită o notificare din colectarea de walleturi.

- un wallet descoperit ca mare câștigător cu sumă mică în cel puțin 2 ZILE diferite (repetarea scade rolul norocului);
- un wallet care trece filtrele complete (monede, tranzacții, rată de succes, ROI, vechime).
Nu decide nimic, nu atinge conturile; `alerting --extra` le trimite o singură dată.

    python -m src.bnd.smart_alerts --descoperite descoperite.csv --out alerte-smart.json
"""

import argparse
import csv
import json
import sys
from pathlib import Path


def alerts_from(descoperite_path) -> list[str]:
    path = Path(descoperite_path) if descoperite_path else None
    if not path or not path.exists():
        return []
    days, passing = {}, set()
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            wallet = (row.get("wallet") or "").strip()
            if not wallet:
                continue
            days.setdefault(wallet, set()).add((row.get("time") or "")[:10])
            if row.get("passes") == "1":
                passing.add(wallet)
    out = []
    for wallet in sorted(days):
        short = f"{wallet[:6]}…{wallet[-4:]}"
        if len(days[wallet]) >= 2:
            out.append(f"Smart-Money: walletul {short} a reapărut câștigător în {len(days[wallet])} zile diferite")
        if wallet in passing:
            out.append(f"Smart-Money: walletul {short} trece toate filtrele (de verificat manual)")
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="smart_alerts")
    parser.add_argument("--descoperite")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    Path(args.out).write_text(json.dumps({"once": alerts_from(args.descoperite)}, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
