"""Date de context macro și de piață, strânse în arhivă (Market Intelligence): doar colectare, zero decizii.

- **Polymarket**: probabilități implicite ale pieței pentru evenimente viitoare (API public, fără cheie);
- **FRED**: serii macro (dobânzi, randamente, inflație, șomaj), cu `FRED_API_KEY` gratuită; fără cheie se sare peste;
- **SEC EDGAR**: fapte din bilanțuri ale companiilor americane din universul nostru, CU DATA DEPUNERII (fără cheie, doar
  un User-Agent care ne identifică). Cu data depunerii, `pit.filed_as_of` poate reconstitui ce era public la o dată.

Nu intră în decizia niciunui cont și NU sunt date consiliului în timpul testului. Sursele nu au putut fi verificate din
sandbox (rețea restricționată): parserele sunt testate pe exemple, iar `status.json` arată ce a răspuns fiecare sursă.

    python -m src.bnd.macro_data --out arhiva [--only polymarket,fred,edgar]
"""

import argparse
import csv
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .context_data import merge_csv

POLYMARKET_URL = "https://gamma-api.polymarket.com/markets?active=true&closed=false&order=volume&ascending=false&limit=30"
FRED_URL = ("https://api.stlouisfed.org/fred/series/observations?series_id={series}&api_key={key}&file_type=json"
            "&observation_start={start}")
EDGAR_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
EDGAR_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
# SEC cere un User-Agent cu un contact real ("Nume contact@domeniu"); fără el răspunde 403. Se setează din variabila
# de depozit EDGAR_USER_AGENT (nu punem o adresă în cod). Gol = identificarea cu depozitul, pe care SEC o poate refuza.
USER_AGENT = (os.getenv("EDGAR_USER_AGENT") or "").strip() or \
    "BND Global Trading Intelligence research (https://github.com/Leontim696/BND-Global-Trading-Intelligence)"
FRED_SERIES = ("FEDFUNDS", "DGS2", "DGS10", "CPIAUCSL", "UNRATE", "VIXCLS", "T10Y2Y")
EDGAR_TAGS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "NetIncomeLoss", "OperatingIncomeLoss",
              "Assets", "StockholdersEquity", "EarningsPerShareDiluted")
EDGAR_KEEP_DAYS = 800          # istoricul păstrat: ultimele ~2 ani de depuneri


def _get_json(url: str, timeout: float = 40.0, agent: str = USER_AGENT):
    request = Request(url, headers={"User-Agent": agent, "Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:  # nosec B310 - https fix, date publice, doar citire
            return json.loads(response.read(40_000_001))
    except HTTPError as exc:
        raise ValueError(f"{url.split('?')[0]} a răspuns HTTP {exc.code}") from exc
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        raise ValueError(f"{url.split('?')[0]} nu răspunde: {type(exc).__name__}") from exc


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


# --- Polymarket ----------------------------------------------------------------------------

def parse_polymarket(payload, day: str) -> list[list]:
    """Rânduri [cheie, zi, slug, întrebare, p_yes, volum, data_încheierii]; probabilitatea primului rezultat (Yes)."""
    if not isinstance(payload, list):
        raise ValueError("Răspuns Polymarket invalid (nu e listă)")
    rows = []
    for item in payload:
        try:
            slug, question = str(item["slug"]), str(item["question"]).strip()
            prices = item["outcomePrices"]
            prices = json.loads(prices) if isinstance(prices, str) else prices
            outcomes = item.get("outcomes")
            outcomes = json.loads(outcomes) if isinstance(outcomes, str) else outcomes
            p_yes = _number(prices[0])
            if p_yes is None or not 0 <= p_yes <= 1 or (outcomes and str(outcomes[0]).lower() != "yes"):
                continue
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        rows.append([f"{day}|{slug}", day, slug, question, f"{p_yes:.4f}", str(_number(item.get("volume")) or ""),
                     str(item.get("endDate") or "")[:10]])
    if not rows:
        raise ValueError("Polymarket fără piețe valide")
    return rows


# --- FRED ----------------------------------------------------------------------------------

def parse_fred(payload, series: str) -> list[list]:
    """Rânduri [cheie, serie, data, valoare, realtime_start]; valorile lipsă ('.') se sar."""
    try:
        observations = payload["observations"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Răspuns FRED invalid") from exc
    rows = []
    for obs in observations:
        value = _number(obs.get("value"))
        if value is None or not obs.get("date"):
            continue
        vintage = str(obs.get("realtime_start") or "")[:10]
        rows.append([f"{series}|{obs['date']}|{vintage}", series, obs["date"], f"{value:g}", vintage])
    if not rows:
        raise ValueError(f"FRED {series}: fără observații")
    return rows


# --- SEC EDGAR -----------------------------------------------------------------------------

def parse_edgar_tickers(payload) -> dict:
    """ticker -> CIK cu 10 cifre."""
    try:
        return {str(v["ticker"]).upper(): f"{int(v['cik_str']):010d}" for v in payload.values()}
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("Lista de tickere EDGAR invalidă") from exc


def parse_edgar_facts(payload, ticker: str, today: datetime) -> list[list]:
    """Rânduri [cheie, ticker, tag, perioada, valoare, formular, data_depunerii] doar pentru etichetele alese.

    Fiecare fapt are data depunerii; se păstrează toate versiunile (restatările) depuse în ultimele ~2 ani."""
    cutoff = (today - timedelta(days=EDGAR_KEEP_DAYS)).date().isoformat()
    try:
        facts = payload["facts"]["us-gaap"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Fapte EDGAR invalide pentru {ticker}") from exc
    rows = []
    for tag in EDGAR_TAGS:
        for unit_rows in (facts.get(tag) or {}).get("units", {}).values():
            for entry in unit_rows:
                filed, end, value = str(entry.get("filed", ""))[:10], str(entry.get("end", ""))[:10], _number(entry.get("val"))
                if not filed or not end or value is None or filed < cutoff:
                    continue
                rows.append([f"{ticker}|{tag}|{end}|{filed}", ticker, tag, end, f"{value:g}",
                             str(entry.get("form") or ""), filed])
    if not rows:
        raise ValueError(f"EDGAR {ticker}: fără fapte recente")
    return rows


def us_tickers() -> list[str]:
    from .universe import DEFENSE_UNIVERSE, STOCK_UNIVERSE, DEFENSE_CURRENCY
    names = [m.symbol for m in STOCK_UNIVERSE]
    names += [m.symbol for m in DEFENSE_UNIVERSE if DEFENSE_CURRENCY.get(m.name) == "USD" and m.asset_class == "stock"]
    return sorted(set(names))


# --- colectare -----------------------------------------------------------------------------

def collect(out, only=("polymarket", "fred", "edgar"), fetch_json=_get_json, now=None, fred_key=None, tickers=None) -> dict:
    out = Path(out) / "macro"
    out.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now(timezone.utc)
    day = now.date().isoformat()
    status = {"time": now.isoformat(timespec="minutes"), "sources": {}}

    def record(name, work):
        try:
            status["sources"][name] = {"ok": True, **work()}
        except ValueError as exc:
            status["sources"][name] = {"ok": False, "error": str(exc)}

    if "polymarket" in only:
        def poly():
            rows = parse_polymarket(fetch_json(POLYMARKET_URL), day)
            added = merge_csv(out / "polymarket.csv", ["id", "day", "slug", "question", "p_yes", "volume", "end_date"], rows)
            return {"markets": len(rows), "added": added}
        record("polymarket", poly)
    if "fred" in only:
        if not fred_key:
            status["sources"]["fred"] = {"ok": False, "error": "fără cheie FRED_API_KEY"}
        else:
            def fred():
                total = 0
                start = (now - timedelta(days=400)).date().isoformat()
                for series in FRED_SERIES:
                    rows = parse_fred(fetch_json(FRED_URL.format(series=series, key=fred_key, start=start)), series)
                    merge_csv(out / "fred.csv", ["id", "series", "date", "value", "vintage"], rows)
                    total += len(rows)
                return {"rows": total}
            record("fred", fred)
    if "edgar" in only:
        def edgar():
            wanted = tickers or us_tickers()
            ciks = parse_edgar_tickers(fetch_json(EDGAR_TICKERS_URL))
            done, missing = 0, []
            for ticker in wanted:
                if ticker not in ciks:
                    missing.append(ticker)
                    continue
                try:
                    rows = parse_edgar_facts(fetch_json(EDGAR_FACTS_URL.format(cik=ciks[ticker])), ticker, now)
                except ValueError as exc:
                    missing.append(f"{ticker}: {exc}")
                    continue
                merge_csv(out / "edgar.csv", ["id", "ticker", "tag", "end", "value", "form", "filed"], rows)
                done += 1
            if not done:
                raise ValueError("EDGAR: niciun ticker colectat (" + "; ".join(missing[:3]) + ")")
            return {"tickers": done, "missing": missing[:20]}
        record("edgar", edgar)
    (out / "status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    return status


def read_edgar(path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="macro_data")
    parser.add_argument("--out", required=True)
    parser.add_argument("--only", default="polymarket,fred,edgar")
    args = parser.parse_args(argv)
    only = tuple(x.strip() for x in args.only.split(",") if x.strip())
    status = collect(args.out, only, fred_key=os.getenv("FRED_API_KEY") or None)
    failed = [k for k, v in status["sources"].items() if not v["ok"]]
    print(json.dumps({"ok": [k for k in status["sources"] if k not in failed], "failed": failed}))
    for name in failed:
        print(f"::warning::sursa {name}: {status['sources'][name].get('error', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
