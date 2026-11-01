"""Pachetul zilnic pentru Google Drive: un folder pe zi cu investițiile și deciziile consiliului, cu explicații.

Generează fișiere HTML (se încarcă în Drive și devin documente) din datele zilei:
- ``00 Rezumat``: starea contului unic, câte piețe a votat consiliul, costul zilei;
- ``01 Investiții``: pozițiile, ordinele pregătite și execuțiile zilei, cu MOTIVUL fiecărui ordin (semnalul regulilor,
  votul consiliului, semnalul combinat, ponderea și limitele);
- ``02..`` Consiliu pe grupe de piețe: decizia, voturile fiecărui agent și motivul lui.
Doar citire din date existente; nu apelează AI și nu atinge conturile.

    python -m src.bnd.drive_pack --day 2026-11-01 --council consiliu.md --run run.json --signals semnale.json --out folder
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

from . import market_groups

MAX_DOC_CHARS = 21_000
SECTION = re.compile(r"^## (?P<market>[A-Z0-9_]+): \*\*(?P<decision>[^*]+)\*\*(?: \((?P<lean>[^)]*)\))?\s*$")
ROW = re.compile(r"^\| (?P<agent>\w+) \| (?P<vote>BUY|SELL|HOLD) \| (?P<conf>[0-9.]+) \| (?P<reason>.*) \|\s*$")
PRICE = re.compile(r"^Preț (?P<price>[0-9.]+) \((?P<date>[^)]*)\); regula simplă a botului: (?P<bot>[^;]*); cost (?P<cost>[0-9.]+) \$")
VOTE_RO = {"BUY": "cumpără", "SELL": "vinde", "HOLD": "așteaptă"}
SIDE_RO = {"BUY": "cumpără", "SELL": "vinde (short)"}


def parse_council(text: str) -> list[dict]:
    """[{market, decision, lean, price, bot, votes: [{agent, vote, confidence, reason}]}] din raportul zilei."""
    markets, current = [], None
    for line in text.splitlines():
        m = SECTION.match(line)
        if m:
            current = {"market": m["market"], "decision": m["decision"].strip(), "lean": m["lean"] or "", "price": None,
                       "date": "", "bot": "", "votes": []}
            markets.append(current)
            continue
        if current is None:
            continue
        p = PRICE.match(line)
        if p:
            current.update(price=p["price"], date=p["date"], bot=p["bot"])
            continue
        r = ROW.match(line)
        if r:
            current["votes"].append({"agent": r["agent"], "vote": r["vote"], "confidence": r["conf"],
                                     "reason": r["reason"].replace("\\|", "|")})
    return markets


def _tally(votes) -> str:
    counts = {v: sum(1 for x in votes if x["vote"] == v) for v in ("BUY", "SELL", "HOLD")}
    return f"{counts['BUY']} cumpără, {counts['SELL']} vinde, {counts['HOLD']} așteaptă"


def market_html(m: dict) -> str:
    esc = html.escape
    head = f"<h3>{esc(m['market'])}: {esc(m['decision'])}" + (f" ({esc(m['lean'])})" if m["lean"] else "") + "</h3>"
    price = (f"<p>Preț {esc(str(m['price']))} ({esc(m['date'])}); regula simplă a botului: {esc(m['bot'])}. "
             f"Voturi: {_tally(m['votes'])}.</p>") if m["price"] else f"<p>Voturi: {_tally(m['votes'])}.</p>"
    lines = "".join(f"<p><b>{esc(v['agent'])}</b>: {VOTE_RO[v['vote']]} (încredere {esc(v['confidence'])}). {esc(v['reason'])}</p>"
                    for v in m["votes"])
    return head + price + lines


def council_docs(markets: list[dict], day: str, suffix: str = "", first_number: int = 2) -> list[tuple[str, str]]:
    """[(titlu, html)] pe grupe de piețe, fiecare document sub MAX_DOC_CHARS."""
    labels = dict((g["key"], g["label"]) for g in market_groups.labels())
    by_group: dict = {}
    for m in markets:
        by_group.setdefault(market_groups.group_of(m["market"]), []).append(m)
    docs = []
    number = first_number
    for key in [g["key"] for g in market_groups.labels()]:
        items = sorted(by_group.get(key, []), key=lambda m: m["market"])
        if not items:
            continue
        chunk, size = [], 0
        pieces = []
        for m in items:
            block = market_html(m)
            if chunk and size + len(block) > MAX_DOC_CHARS:
                pieces.append(chunk)
                chunk, size = [], 0
            chunk.append((m, block))
            size += len(block)
        pieces.append(chunk)
        for index, group in enumerate(pieces, 1):
            title = f"{number:02d} Consiliu {day}{suffix} - {labels.get(key, key)}" + (f" (partea {index} din {len(pieces)})" if len(pieces) > 1 else "")
            table = "<table border='1' cellpadding='4'><tr><th>Piață</th><th>Decizie</th><th>Voturi</th></tr>" + "".join(
                f"<tr><td>{html.escape(m['market'])}</td><td>{html.escape(m['decision'])}</td><td>{_tally(m['votes'])}</td></tr>"
                for m, _ in group) + "</table>"
            body = f"<html><body><h1>{html.escape(title)}</h1><p>Decizia consiliului AI (5 agenți independenți) și motivul fiecărui agent. " \
                   "Nu se tranzacționează nimic pe baza lor direct: sunt notate și comparate după 5 zile.</p>" + table + \
                   "".join(b for _, b in group) + "</body></html>"
            docs.append((title, body))
            number += 1
    return docs


def investments_html(day: str, run: dict, council_signals: dict, council_votes: dict | None = None) -> str:
    """Explicația fiecărui ordin: semnalul regulilor, votul consiliului, semnalul combinat, ponderea."""
    esc = html.escape
    signals = run.get("signals", {})
    orders = run.get("orders", [])
    ai_weight = 0.5
    rows, explanations = [], []
    for o in sorted(orders, key=lambda o: -abs(o["weight_to"] - o["weight_from"])):
        market = o["market"]
        combined = signals.get(market)
        ai = council_signals.get(market)
        rule = None if combined is None else (2 * combined - ai if ai is not None else combined)
        net = (council_votes or {}).get(market)
        side = SIDE_RO.get(o["side"], o["side"])
        rows.append(f"<tr><td>{esc(market)}</td><td>{side}</td><td>{o['quantity']:.4g}</td><td>{o['price']:.4g}</td>"
                    f"<td>{100 * o['weight_to']:+.1f}%</td><td>{'' if o.get('stop_loss') is None else format(o['stop_loss'], '.4g')}</td>"
                    f"<td>{o['status']}</td></tr>")
        parts = []
        if rule is not None:
            parts.append(f"regulile (tendință/regim) dau semnal {rule:+.2f}")
        parts.append("consiliul AI nu a avut vot pe această piață" if ai is None else
                     f"consiliul dă semnal {ai:+.2f}" + (f" (voturi nete {net:+d})" if net is not None else ""))
        if combined is not None:
            parts.append(f"semnalul combinat ({int((1 - ai_weight) * 100)}% reguli + {int(ai_weight * 100)}% consiliu) e {combined:+.2f}")
        parts.append(f"ponderea țintă în cont: {100 * o['weight_to']:+.1f}% (de la {100 * o['weight_from']:+.1f}%)")
        if o.get("risk_capped"):
            parts.append("limitată de plafonul de risc")
        explanations.append(f"<p><b>{esc(market)}</b>, {side}: " + "; ".join(parts) + ".</p>")
    held = [f"{esc(p['symbol'])}" for p in run.get("positions", [])] if "positions" in run else []
    return (f"<html><body><h1>01 Investiții {esc(day)} (contul unic, bani virtuali)</h1>"
            f"<p>Valoare cont: <b>{run.get('equity', 0):,.2f} {esc(str(run.get('currency', '')))}</b>; bani liberi {run.get('cash', 0):,.2f}; "
            f"expunere brută {run.get('gross_leverage', 0):.2f}x; oprire de siguranță: {'ACTIVĂ' if run.get('kill_switch') else 'oprită (în regulă)'}.</p>"
            f"<p>Strategia „{esc(str(run.get('strategy', '')))}”: jumătate reguli (regime_switch, long și short), jumătate vot al consiliului AI. "
            f"Limite: leverage maxim {run.get('settings', {}).get('max_leverage')}x, maxim {100 * (run.get('settings', {}).get('max_weight') or 0):.0f}% pe piață, "
            f"{run.get('settings', {}).get('max_sector')}% pe clasă, volatilitate-țintă {run.get('settings', {}).get('portfolio_vol')}%.</p>"
            f"<p>Poziții deschise: {len(held) if held else 0}. Ordine pregătite (se execută la deschiderea următoare): {len(orders)}.</p>"
            "<table border='1' cellpadding='4'><tr><th>Piață</th><th>Direcție</th><th>Cantitate</th><th>Preț</th><th>Pondere</th><th>Stop</th><th>Stare</th></tr>"
            + "".join(rows) + "</table><h2>De ce fiecare ordin</h2>" + "".join(explanations) + "</body></html>")


def summary_html(day: str, markets: list[dict], run: dict | None, cost_line: str = "") -> str:
    counts = {}
    for m in markets:
        counts[m["decision"]] = counts.get(m["decision"], 0) + 1
    decided = ", ".join(f"{n} × {html.escape(d)}" for d, n in sorted(counts.items(), key=lambda kv: -kv[1]))
    account = ""
    if run:
        account = (f"<p>Contul unic: {run.get('equity', 0):,.2f} {html.escape(str(run.get('currency', '')))}, "
                   f"{len(run.get('orders', []))} ordine pregătite.</p>")
    return (f"<html><body><h1>00 Rezumat {html.escape(day)}</h1>{account}"
            f"<p>Consiliul AI a votat {len(markets)} piețe: {decided}. {html.escape(cost_line)}</p>"
            "<p>Documentele din acest folder: 01 Investiții (cu motivul fiecărui ordin) și 02… Consiliu pe grupe de piețe "
            "(decizia și motivul fiecărui agent). Rapoartele orare ale contului sunt în folderul principal.</p></body></html>")


def merge_reports(texts: list[str]) -> str:
    """Rapoartele aceleiași zile (mai multe rulări) într-unul: prima decizie a fiecărei piețe rămâne; „decis deja azi” se sare."""
    seen, parts = set(), []
    for text in texts:
        for m in parse_council(text):
            if m["market"] not in seen:
                seen.add(m["market"])
                votes = "".join(f"| {v['agent']} | {v['vote']} | {v['confidence']} | {v['reason'].replace('|', chr(92) + '|')} |\n" for v in m["votes"])
                lean = f" ({m['lean']})" if m["lean"] else ""
                price = f"Preț {m['price']} ({m['date']}); regula simplă a botului: {m['bot']}; cost 0.000 $.\n" if m["price"] else ""
                parts.append(f"## {m['market']}: **{m['decision']}**{lean}\n{price}\n| Agent | Vot | Încredere | Motiv |\n|---|---|---:|---|\n{votes}")
    return "\n".join(parts)


def run_fingerprint(run: dict | None) -> str:
    """Amprenta ordinelor și valorii contului: o pagină nouă de investiții se face doar dacă s-a schimbat ceva."""
    import hashlib
    if not run:
        return ""
    body = json.dumps({"equity": run.get("equity"), "orders": run.get("orders"), "weights": run.get("weights")},
                      sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:12]


def build_day(day: str, council_text: str, run: dict | None, council_signals: dict, out: Path,
              council_votes: dict | None = None, cost_line: str = "", state: dict | None = None,
              suffix: str = "") -> tuple[list[str], dict]:
    """Documentele zilei. `state` = ce s-a urcat deja pentru ziua asta ({"markets": [...], "investitii": amprentă}):
    se generează doar piețele noi și, dacă s-a schimbat contul, o nouă pagină de investiții. Întoarce (titluri, stare nouă)."""
    out.mkdir(parents=True, exist_ok=True)
    state = state or {}
    done = set(state.get("markets", []))
    markets = [m for m in parse_council(council_text) if m["market"] not in done]
    first = not state
    files = []
    if first:
        files.append((f"00 Rezumat {day}{suffix}", summary_html(day, markets, run, cost_line)))
    fingerprint = run_fingerprint(run)
    if run and fingerprint != state.get("investitii"):
        files.append((f"01 Investiții {day}{suffix}", investments_html(day, run, council_signals, council_votes)))
    files += council_docs(markets, day, suffix, first_number=2 + (0 if first else 10))
    names = []
    for title, body in files:
        (out / f"{title}.html").write_text(body, encoding="utf-8")
        names.append(title)
    new_state = {"markets": sorted(done | {m["market"] for m in markets}), "investitii": fingerprint or state.get("investitii", "")}
    return names, new_state


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="drive_pack")
    parser.add_argument("--day", required=True)
    parser.add_argument("--council", required=True)
    parser.add_argument("--run")
    parser.add_argument("--signals")
    parser.add_argument("--out", required=True)
    parser.add_argument("--cost-line", default="")
    parser.add_argument("--state", help="JSON cu ce s-a urcat deja ({ziua: {markets, investitii}}); se citește, nu se scrie")
    parser.add_argument("--suffix", default="", help="adaos la titlu pentru completările aceleiași zile, de exemplu ' (seara)'")
    parser.add_argument("--mark-uploaded", action="store_true", help="scrie în --state ce tocmai s-a generat (după urcare reușită)")
    args = parser.parse_args(argv)
    run = json.loads(Path(args.run).read_text(encoding="utf-8")) if args.run and Path(args.run).exists() else None
    signals = json.loads(Path(args.signals).read_text(encoding="utf-8")).get("signals", {}) if args.signals and Path(args.signals).exists() else {}
    state_path = Path(args.state) if args.state else None
    all_state = json.loads(state_path.read_text(encoding="utf-8")) if state_path and state_path.exists() else {}
    names, new_state = build_day(args.day, Path(args.council).read_text(encoding="utf-8"), run, signals, Path(args.out),
                                 cost_line=args.cost_line, state=all_state.get(args.day), suffix=args.suffix)
    if args.mark_uploaded and state_path:
        all_state[args.day] = new_state
        state_path.write_text(json.dumps(all_state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(names, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
