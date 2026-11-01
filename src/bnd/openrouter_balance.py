"""Soldul real al cheii OpenRouter, citit direct de la furnizor (doar citire, gratuit).

Folosește două puncte de acces care nu consumă credit: `/api/v1/key` (limita și consumul cheii) și
`/api/v1/credits` (credite cumpărate și folosite). Soldul efectiv = minimul dintre ce mai are voie
cheia și ce credit a mai rămas în cont. Se salvează doar numere (cheia nu se scrie și nu se afișează
nicăieri). Dacă furnizorul nu răspunde, se notează eroarea și aplicația folosește ultima valoare
confirmată.

    OPENROUTER_API_KEY=... python -m src.bnd.openrouter_balance --out balance.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://openrouter.ai/api/v1"


def _get(path: str, key: str, timeout: float = 20.0) -> dict:
    request = Request(BASE + path, headers={"Authorization": "Bearer " + key,
                                            "User-Agent": "BND-balance/1"}, method="GET")
    try:
        # Reviewed: fixed https URL constant, read-only, the key is never logged.
        with urlopen(request, timeout=timeout) as response:  # nosec B310
            return json.loads(response.read(200_000))["data"]
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, OSError) as exc:
        raise ValueError(f"{path}: {type(exc).__name__}") from exc


def _num(value):
    return None if value is None else float(value)


def read_balance(key: str, get=_get) -> dict:
    result = {"time": datetime.now(timezone.utc).isoformat(timespec="minutes"), "ok": False}
    candidates = []
    try:
        info = get("/key", key)
        limit, usage = _num(info.get("limit")), _num(info.get("usage")) or 0.0
        remaining = _num(info.get("limit_remaining"))
        if remaining is None and limit is not None:
            remaining = limit - usage
        result.update(key_limit=limit, key_usage=usage, key_remaining=remaining)
        if remaining is not None:
            candidates.append(remaining)
    except ValueError as exc:
        result["key_error"] = str(exc)
    try:
        credits = get("/credits", key)
        total, used = _num(credits.get("total_credits")), _num(credits.get("total_usage"))
        result.update(credits_total=total, credits_used=used)
        if total is not None and used is not None:
            result["credits_remaining"] = total - used
            candidates.append(total - used)
    except ValueError as exc:
        result["credits_error"] = str(exc)
    if candidates:
        result.update(ok=True, effective_remaining=round(min(candidates), 4))
    return result


def main(argv=None, get=_get) -> int:
    parser = argparse.ArgumentParser(prog="openrouter_balance")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        result = {"time": datetime.now(timezone.utc).isoformat(timespec="minutes"), "ok": False,
                  "error": "OPENROUTER_API_KEY lipsește"}
    else:
        result = read_balance(key, get)
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k in ("ok", "effective_remaining")}))
    return 0          # un eșec de citire nu oprește restul


if __name__ == "__main__":
    sys.exit(main())
