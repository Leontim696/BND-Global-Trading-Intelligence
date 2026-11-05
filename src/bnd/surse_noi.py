"""Surse noi de date, gratuite, cerute de proprietar pe 5.11.2026: DOAR colectare zilnică pentru analiză după 1.12.

Nu intră în decizia niciunui cont și nu sunt date consiliului AI (ar costa tokeni și ar schimba testul oficial).
Fiecare sursă e „best effort”: un eșec se notează în `surse-noi-status.json` și nu oprește restul.

    deribit/      volatilitatea așteptată (DVOL, istoric zilnic) și raportul put/call pe opțiuni (BTC, ETH)
    pozitionare/  open interest, raport long/short și volumul cumpărătorilor agresivi pe futures (OKX), pe monede
    cot/          raportul COT al CFTC (săptămânal): pozițiile speculatorilor și ale comercianților pe aur, petrol, indici,
                  valute, obligațiuni și Bitcoin CME
    defi/         totalul stablecoin-urilor în circulație și banii blocați în DeFi (DefiLlama)

Lichidările pe futures nu au istoric zilnic gratuit (doar ultimele ordine), deci lipsesc deocamdată. Binance Futures
refuză adresele din SUA (unde rulează GitHub), de aceea poziționarea vine de la OKX.

    python -m src.bnd.surse_noi --out arhiva
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

from .context_data import _get_json, merge_csv

DERIBIT = "https://www.deribit.com/api/v2/public/"
OKX_RUBIK = "https://www.okx.com/api/v5/rubik/stat/"
CFTC = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
STABLECOINS = "https://stablecoins.llama.fi/stablecoincharts/all"
DEFI_TVL = "https://api.llama.fi/v2/historicalChainTvl"

DERIBIT_COINS = ("BTC", "ETH")
OKX_COINS = {"BITCOIN": "BTC", "ETHEREUM": "ETH", "SOLANA": "SOL", "XRP": "XRP", "BNB": "BNB", "DOGE": "DOGE"}
# Codurile contractelor CFTC (raportul „Legacy, futures only”) pentru piețele noastre.
COT = {"GOLD": "088691", "SILVER": "084691", "CRUDE_OIL": "067651", "NATURAL_GAS": "023651", "COPPER": "085692",
       "SP500": "13874A", "NASDAQ100": "209742", "EURUSD": "099741", "GBPUSD": "096742", "USDJPY": "097741",
       "AUDUSD": "232741", "USDCHF": "092741", "USDCAD": "090741", "US10Y_NOTE": "043602", "BITCOIN": "133741"}


def _day(ms) -> str:
    return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).date().isoformat()


# ---------------------------------------------------------------- Deribit

def parse_dvol(payload) -> list[tuple]:
    try:
        return sorted({(_day(r[0]), round(float(r[4]), 2)) for r in payload["result"]["data"]})
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ValueError("Răspuns Deribit DVOL invalid") from exc


def parse_options(payload, today: str) -> tuple:
    """(zi, put/call pe open interest, put/call pe volum, open interest total) din cartea de opțiuni."""
    oi = {"P": 0.0, "C": 0.0}
    vol = {"P": 0.0, "C": 0.0}
    try:
        for r in payload["result"]:
            kind = r["instrument_name"].rsplit("-", 1)[-1]
            if kind in oi:
                oi[kind] += float(r.get("open_interest") or 0)
                vol[kind] += float(r.get("volume") or 0)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Răspuns Deribit opțiuni invalid") from exc
    if not oi["C"]:
        raise ValueError("fără opțiuni call")
    return (today, round(oi["P"] / oi["C"], 4), round(vol["P"] / vol["C"], 4) if vol["C"] else "",
            round(oi["P"] + oi["C"], 2))


# ---------------------------------------------------------------- OKX (poziționare pe futures)

def parse_okx_rows(payload) -> dict:
    try:
        if str(payload.get("code", "0")) != "0":
            raise ValueError(payload.get("msg") or "cod de eroare")
        return {_day(r[0]): r[1:] for r in payload["data"]}
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError("Răspuns OKX invalid") from exc


def positioning_rows(oi: dict, ratio: dict, taker: dict) -> list[tuple]:
    days = sorted(set(oi) | set(ratio) | set(taker))
    out = []
    for d in days:
        o, r, t = oi.get(d, ["", ""]), ratio.get(d, [""]), taker.get(d, ["", ""])
        out.append((d, o[0], o[1] if len(o) > 1 else "", r[0], t[1] if len(t) > 1 else "", t[0]))
    return out


# ---------------------------------------------------------------- CFTC COT

def cot_url(code: str, since: str) -> str:
    return CFTC + "?" + urlencode({
        "$where": f"cftc_contract_market_code='{code}' AND report_date_as_yyyy_mm_dd >= '{since}'",
        "$order": "report_date_as_yyyy_mm_dd", "$limit": "1000"})


def parse_cot(rows) -> list[tuple]:
    out = []
    try:
        for r in rows:
            day = r["report_date_as_yyyy_mm_dd"][:10]
            sl, ss = float(r["noncomm_positions_long_all"]), float(r["noncomm_positions_short_all"])
            cl, cs = float(r["comm_positions_long_all"]), float(r["comm_positions_short_all"])
            out.append((day, float(r["open_interest_all"]), sl, ss, sl - ss, cl, cs))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Răspuns CFTC invalid") from exc
    return sorted(out)


# ---------------------------------------------------------------- DefiLlama

def parse_stablecoins(payload) -> list[tuple]:
    try:
        return sorted((datetime.fromtimestamp(int(r["date"]), timezone.utc).date().isoformat(),
                       round(float(r["totalCirculatingUSD"]["peggedUSD"]), 0)) for r in payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Răspuns DefiLlama stablecoins invalid") from exc


def parse_tvl(payload) -> list[tuple]:
    try:
        return sorted((datetime.fromtimestamp(int(r["date"]), timezone.utc).date().isoformat(),
                       round(float(r["tvl"]), 0)) for r in payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Răspuns DefiLlama TVL invalid") from exc


# ---------------------------------------------------------------- colectare

def collect(out, fetch_json=_get_json, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    out = Path(out)
    today = now.date().isoformat()
    status = {"time": now.isoformat(timespec="minutes"), "sources": {}}

    def run(name, job):
        try:
            added, last = job()
            status["sources"][name] = {"ok": True, "added": added, "last": last}
        except ValueError as exc:
            status["sources"][name] = {"ok": False, "error": str(exc)[:200]}

    start_ms = int((now - timedelta(days=400)).timestamp() * 1000)
    for coin in DERIBIT_COINS:
        def dvol(coin=coin):
            rows = parse_dvol(fetch_json(DERIBIT + "get_volatility_index_data?" + urlencode({
                "currency": coin, "start_timestamp": start_ms, "end_timestamp": int(now.timestamp() * 1000),
                "resolution": "1D"})))
            if not rows:
                raise ValueError("fără rânduri")
            return merge_csv(out / "deribit" / f"dvol_{coin}.csv", ["date", "dvol"], rows), rows[-1][0]

        def options(coin=coin):
            row = parse_options(fetch_json(DERIBIT + "get_book_summary_by_currency?" + urlencode(
                {"currency": coin, "kind": "option"})), today)
            return merge_csv(out / "deribit" / f"optiuni_{coin}.csv",
                             ["date", "put_call_oi", "put_call_volum", "open_interest"], [row]), row[0]
        run(f"deribit_dvol_{coin}", dvol)
        run(f"deribit_optiuni_{coin}", options)

    for name, ccy in OKX_COINS.items():
        def positioning(ccy=ccy, name=name):
            oi = parse_okx_rows(fetch_json(OKX_RUBIK + "contracts/open-interest-volume?" + urlencode(
                {"ccy": ccy, "period": "1D"})))
            ratio = parse_okx_rows(fetch_json(OKX_RUBIK + "contracts/long-short-account-ratio?" + urlencode(
                {"ccy": ccy, "period": "1D"})))
            taker = parse_okx_rows(fetch_json(OKX_RUBIK + "taker-volume?" + urlencode(
                {"ccy": ccy, "instType": "CONTRACTS", "period": "1D"})))
            rows = positioning_rows(oi, ratio, taker)
            if not rows:
                raise ValueError("fără rânduri")
            return merge_csv(out / "pozitionare" / f"{name}.csv",
                             ["date", "open_interest_usd", "volum_usd", "long_short_conturi", "taker_cumparare",
                              "taker_vanzare"], rows), rows[-1][0]
        run(f"pozitionare_{name}", positioning)

    since = (now.date() - timedelta(days=3 * 365)).isoformat()
    for name, code in COT.items():
        def cot(name=name, code=code):
            rows = parse_cot(fetch_json(cot_url(code, since)))
            if not rows:
                raise ValueError("fără rânduri (cod CFTC greșit?)")
            return merge_csv(out / "cot" / f"{name}.csv",
                             ["date", "open_interest", "spec_long", "spec_short", "spec_net", "comerciali_long",
                              "comerciali_short"], rows), rows[-1][0]
        run(f"cot_{name}", cot)

    def stable():
        rows = parse_stablecoins(fetch_json(STABLECOINS))
        return merge_csv(out / "defi" / "stablecoins.csv", ["date", "total_usd"], rows), rows[-1][0]

    def tvl():
        rows = parse_tvl(fetch_json(DEFI_TVL))
        return merge_csv(out / "defi" / "tvl.csv", ["date", "tvl_usd"], rows), rows[-1][0]
    run("defi_stablecoins", stable)
    run("defi_tvl", tvl)

    out.mkdir(parents=True, exist_ok=True)
    (out / "surse-noi-status.json").write_text(json.dumps(status, indent=1, ensure_ascii=False), encoding="utf-8")
    return status


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="surse_noi")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    status = collect(args.out)
    ok = sorted(k for k, v in status["sources"].items() if v["ok"])
    failed = sorted(k for k in status["sources"] if k not in ok)
    print(json.dumps({"ok": len(ok), "failed": failed}, ensure_ascii=False))
    for name in failed:
        print(f"::warning::sursa {name} nu a răspuns: {status['sources'][name]['error']}")
    return 0           # un eșec de sursă nu oprește arhivarea restului


if __name__ == "__main__":
    sys.exit(main())
