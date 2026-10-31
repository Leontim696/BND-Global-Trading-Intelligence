"""Prețurile de acum pentru toate piețele folosite de conturile virtuale.

Scrie un JSON mic (nume piață -> [preț, ora]) pe care aplicația de pe telefon îl
folosește ca să arate valoarea conturilor la prețul de acum, nu la ultima
închidere. Doar citire de prețuri publice (Yahoo); nu tranzacționează.

    python -m src.bnd.quotes_snapshot --out quotes.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .report_card import quotes_for
from .universe import CRYPTO_UNIVERSE, ETF_UNIVERSE


def snapshot(fetch=None) -> dict:
    extra = {} if fetch is None else {"fetch": fetch}
    found = {}
    for universe, markets in (("etf", ETF_UNIVERSE), ("crypto", CRYPTO_UNIVERSE)):
        found.update(quotes_for([m.name for m in markets], universe=universe, **extra))
    return {"time": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "quotes": {name: [price, when.isoformat()] for name, (price, when) in found.items()}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="quotes_snapshot")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    Path(args.out).write_text(json.dumps(snapshot()), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
