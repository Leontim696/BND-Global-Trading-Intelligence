"""Calendar economic, strâns în arhivă (Market Intelligence, pasul 1): doar colectare.

Evenimente de pe piață (dobânzi, inflație, ocupare etc.) cu țara, impactul (Low/Medium/High),
prognoza și valoarea anterioară. Sursa e un calendar săptămânal public, gratuit, în format JSON.
Nu intră în decizia niciunui cont și NU e dat consiliului în timpul testului de 16 zile: ar schimba
întrebarea pusă agenților. Rămâne în arhivă pentru analiza „cu sursă / fără sursă” de după test.

Informația confirmată (ora, țara, titlul, prognoza oficială) e păstrată separat de orice
interpretare: aici nu există interpretare AI. Fișierul se completează săptămânal, fără dubluri;
o nouă citire actualizează prognoza unui eveniment deja salvat.

    python -m src.bnd.calendar_data --out arhiva
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .context_data import _get_json, merge_csv

URLS = ("https://nfs.faireconomy.media/ff_calendar_thisweek.json",
        "https://nfs.faireconomy.media/ff_calendar_nextweek.json")
HEADER = ["id", "time_utc", "country", "title", "impact", "forecast", "previous"]
IMPACTS = ("Low", "Medium", "High", "Holiday")


def parse(payload) -> list[list]:
    """Rânduri [id, time_utc, country, title, impact, forecast, previous], sortate în timp."""
    if not isinstance(payload, list):
        raise ValueError("Răspuns calendar invalid (nu e listă)")
    rows = []
    for item in payload:
        try:
            when = datetime.fromisoformat(str(item["date"]).replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            when = when.astimezone(timezone.utc)
            title, country = str(item["title"]).strip(), str(item["country"]).strip()
            impact = str(item.get("impact", "")).strip().capitalize()
        except (KeyError, TypeError, ValueError):
            continue                      # un rând stricat nu strică restul
        if not title or not country or impact not in IMPACTS:
            continue
        stamp = when.isoformat(timespec="minutes")
        rows.append([f"{stamp}|{country}|{title}", stamp, country, title, impact,
                     str(item.get("forecast") or ""), str(item.get("previous") or "")])
    if not rows:
        raise ValueError("Calendar fără evenimente valide")
    return sorted(rows, key=lambda r: r[1])


def collect(out, fetch_json=_get_json) -> dict:
    out = Path(out)
    status = {"time": datetime.now(timezone.utc).isoformat(timespec="minutes"), "sources": {}}
    for url in URLS:
        name = url.rsplit("/", 1)[-1].removesuffix(".json")
        try:
            rows = parse(fetch_json(url))
            added = merge_csv(out / "calendar" / "economic.csv", HEADER, rows)
            status["sources"][name] = {"ok": True, "events": len(rows), "added": added,
                                       "last": rows[-1][1]}
        except ValueError as exc:
            status["sources"][name] = {"ok": False, "error": str(exc)}
    out.mkdir(parents=True, exist_ok=True)
    (out / "calendar-status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False))
    return status


def upcoming(path, now: datetime, hours: int = 48, impacts=("High",), countries=None) -> list[dict]:
    """Evenimentele din următoarele `hours` ore (doar informare, de exemplu pentru raport)."""
    path = Path(path)
    if not path.exists():
        return []
    import csv
    end = now + timedelta(hours=hours)
    found = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                when = datetime.fromisoformat(row["time_utc"])
            except (KeyError, ValueError):
                continue
            if now <= when <= end and row["impact"] in impacts and (not countries or row["country"] in countries):
                found.append({"time": row["time_utc"], "country": row["country"], "title": row["title"],
                              "impact": row["impact"], "forecast": row["forecast"], "previous": row["previous"]})
    return sorted(found, key=lambda e: e["time"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="calendar_data")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    status = collect(args.out)
    ok = [k for k, v in status["sources"].items() if v["ok"]]
    print(json.dumps({"ok": ok, "failed": [k for k in status["sources"] if k not in ok]}))
    return 0               # un eșec de sursă nu oprește arhivarea


if __name__ == "__main__":
    sys.exit(main())
