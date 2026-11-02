"""Semnale pentru contul virtual de cripto, din votul consiliului AI.

Nu face apeluri plătite: citește deciziile pe care consiliul zilnic (în umbră)
le-a luat deja azi pentru monedele alese. Semnalul unei monede:

    net = voturi BUY − voturi SELL (HOLD nu contează)
    semnal = semn(net) × min(1, |net| / 2)      # 1 vot net = 0,5; 2 sau mai multe = 1

O monedă fără decizie de azi nu apare în fișier: botul îi lasă poziția cum e.
Doar bani virtuali.

    python -m src.bnd.crypto_signals --registry registry.sqlite --out semnale.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .decision_registry import DecisionRegistry

DEFAULT_COINS = ("BITCOIN", "ETHEREUM", "SOLANA", "BNB", "XRP")
MISSING_WARN_SHARE = 0.2      # peste atât din piețe fără decizie azi => avertisment în jurnal


def signal_from_meta(meta: dict) -> float:
    net = meta.get("net")
    if net is None:                      # decizii mai vechi: doar direcția
        net = meta.get("lean", 0)
    net = int(net)
    if net == 0:
        return 0.0
    return (1.0 if net > 0 else -1.0) * min(1.0, abs(net) / 2)


def build_signals(registry: DecisionRegistry, coins, day: str) -> dict:
    signals, missing = {}, []
    for coin in coins:
        meta = registry.meta(f"{day}:{coin}")
        if meta is None:
            missing.append(coin)
        else:
            if "net" not in meta and "lean" not in meta:   # decizii făcute înainte de aceste câmpuri
                meta = {**meta, "net": registry.net_votes(f"{day}:{coin}")}
            signals[coin] = signal_from_meta(meta)
    return {"date": day, "signals": signals, "missing": missing}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="crypto_signals")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--coins", default=",".join(DEFAULT_COINS))
    parser.add_argument("--day", help="AAAA-LL-ZZ (UTC), implicit azi")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    day = args.day or datetime.now(timezone.utc).date().isoformat()
    if not Path(args.registry).exists():
        result = {"date": day, "signals": {}, "missing": args.coins.split(",")}
    else:
        coins = [c.strip().upper() for c in args.coins.split(",") if c.strip()]
        result = build_signals(DecisionRegistry(args.registry), coins, day)
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    wanted = len(result["signals"]) + len(result["missing"])
    if wanted and len(result["missing"]) / wanted > MISSING_WARN_SHARE:
        # Fără votul consiliului de azi, contul hibrid ar decide pe tăcute doar pe reguli: măcar să se vadă în jurnal.
        print(f"::warning::Consiliul nu are decizii pentru {len(result['missing'])} din {wanted} piețe în ziua {day} "
              "(rulare întârziată peste miezul nopții UTC sau consiliul nu a publicat încă?)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
