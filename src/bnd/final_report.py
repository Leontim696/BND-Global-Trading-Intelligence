"""Raportul testului oficial (31.10–30.11.2026; preliminar pe 17.11): doar citire, nu tranzacționează.

Adună într-un singur document, cu structură fixată dinainte (vezi docs/RAPORT_FINAL.md):
contul unic (curba de capital, randament, scădere maximă, execuții, comisioane),
comparația cu „cumperi și ții” S&P 500 pe aceeași fereastră, deciziile încheiate ale
consiliului AI (din council_analytics), costul AI și verdictul după criterii stabilite
ÎNAINTE de a vedea rezultatele. Lipsa datelor se spune explicit, nu se ascunde.

    python -m src.bnd.final_report --unic paper.sqlite --registry registry.sqlite \
        [--costs costs.sqlite] [--benchmark SP500.csv] --out raport-final [--end 2026-11-30] [--preliminar]

Scrie <out>.md și <out>.html (UTC peste tot).
"""

import argparse
import html
import json
import sqlite3
import sys
from datetime import date, datetime, timezone
from itertools import pairwise
from pathlib import Path

from . import council_analytics
from .market_data import MarketDataError, load_csv

TEST_START = date(2026, 10, 31)
TEST_END = date(2026, 11, 30)
PRELIMINARY_END = date(2026, 11, 16)
# Criterii fixate pe 2.11.2026, înainte de rezultate (pre-înregistrare). Nu se schimbă după.
MIN_SETTLED = council_analytics.MIN_SAMPLE
MAX_P = 0.05


def _ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def account(path) -> dict:
    """Curba de capital din rulările zilnice, execuțiile și pozițiile deschise."""
    db = _ro(path)
    try:
        acc = db.execute("SELECT initial_capital, currency, kill_switch, kill_reason FROM account").fetchone()
        runs = [json.loads(p) for (p,) in db.execute(
            "SELECT payload FROM journal WHERE kind='daily_run' ORDER BY id")]
        fills = db.execute("SELECT symbol, quantity, price, fee, time FROM fills ORDER BY time").fetchall()
        positions = db.execute("SELECT symbol, quantity, avg_price FROM positions ORDER BY symbol").fetchall()
    finally:
        db.close()
    by_day = {}
    for r in runs:                       # ultima rulare a zilei câștigă
        by_day[r["time"][:10]] = r["equity"]
    curve = sorted(by_day.items())
    start = acc[0]
    values = [start] + [v for _, v in curve]
    peak, drawdown = values[0], 0.0
    for v in values:
        peak = max(peak, v)
        drawdown = max(drawdown, 1 - v / peak)
    daily = [100 * (b / a - 1) for a, b in pairwise(values) if a > 0]
    end = values[-1]
    return {"initial": start, "currency": acc[1], "kill_switch": bool(acc[2]), "kill_reason": acc[3],
            "curve": curve, "final": end, "return_pct": 100 * (end / start - 1) if start else None,
            "max_drawdown_pct": 100 * drawdown, "days": len(curve),
            "best_day_pct": max(daily) if daily else None, "worst_day_pct": min(daily) if daily else None,
            "fills": len(fills), "fees": sum(f[3] for f in fills),
            "positions": [{"symbol": s, "quantity": q, "avg_price": p} for s, q, p in positions]}


def benchmark(path, start: date, end: date) -> dict | None:
    """„Cumperi și ții” pe aceeași fereastră: ultima închidere înainte de start → ultima până la end."""
    try:
        candles = load_csv(path)
    except (MarketDataError, OSError, ValueError):
        return None
    before = [c for c in candles if c.open_time.date() < start]
    window = [c for c in candles if c.open_time.date() <= end]
    if not before or not window or window[-1].open_time.date() < start:
        return None
    a, b = before[-1], window[-1]
    return {"from": a.open_time.date().isoformat(), "to": b.open_time.date().isoformat(),
            "return_pct": 100 * (b.close / a.close - 1)}


def ai_cost(path) -> float | None:
    if not path or not Path(path).exists():
        return None
    db = _ro(path)
    try:
        row = db.execute("SELECT COALESCE(SUM(CAST(cost_usd AS REAL)), 0) FROM usage_records").fetchone()
    except sqlite3.Error:
        return None
    finally:
        db.close()
    return float(row[0])


def verdict(acc: dict, bench: dict | None, council: dict) -> dict:
    """Aplică criteriile pre-înregistrate. Toate trebuie îndeplinite; chiar și atunci e doar un indiciu."""
    hybrid = council["strategies"]["hybrid"]
    calls, rate = hybrid["calls"], hybrid["hit_rate"]
    wins = round(rate * calls) if rate is not None else 0
    p = council_analytics._sign_test_p(wins, calls - wins) if calls else None
    checks = [
        ("Contul unic bate S&P 500 „cumperi și ții” pe aceeași fereastră",
         None if bench is None or acc["return_pct"] is None else acc["return_pct"] > bench["return_pct"]),
        (f"Cel puțin {MIN_SETTLED} decizii hibride încheiate", calls >= MIN_SETTLED),
        ("Rata de reușită a hibridului peste 50%", None if rate is None else rate > 0.5),
        (f"Testul semnului: p < {MAX_P}", None if p is None else p < MAX_P),
    ]
    passed = all(ok is True for _, ok in checks)
    text = ("Indiciu de avantaj (NU dovadă): toate criteriile sunt îndeplinite, dar câteva săptămâni și decizii corelate "
            "între piețe nu ajung pentru o concluzie. Urmează un test mai lung, cu aceleași reguli."
            if passed else
            "Fără dovezi de avantaj: cel puțin un criteriu pre-înregistrat nu e îndeplinit sau nu are date.")
    return {"checks": checks, "sign_test_p": p, "passed": passed, "text": text}


def _fmt(x, digits=2, suffix=""):
    return "–" if x is None else f"{x:,.{digits}f}{suffix}"


def _mark(ok):
    return "da" if ok is True else "nu" if ok is False else "fără date"


def control_comparison(acc: dict, ctrl: dict | None) -> dict | None:
    """Contul unic față de contul de control (doar reguli), pe aceeași fereastră: de la pornirea controlului."""
    if not ctrl or not ctrl["curve"]:
        return None
    first = ctrl["curve"][0][0]
    before = [v for d, v in acc["curve"] if d < first]
    base = before[-1] if before else acc["initial"]
    unic_ret = 100 * (acc["final"] / base - 1) if base else None
    ctrl_ret = ctrl["return_pct"]
    diff = None if unic_ret is None or ctrl_ret is None else unic_ret - ctrl_ret
    return {"from": first, "days": ctrl["days"], "unic_pct": unic_ret, "control_pct": ctrl_ret, "diff_pct": diff,
            "unic_dd": acc["max_drawdown_pct"], "control_dd": ctrl["max_drawdown_pct"]}


def _control_blocks(c: dict | None, cost: float | None) -> list:
    if not c:
        return ["Contul de control (doar reguli, pornit pe 4.11.2026) nu are încă rulări zilnice."]
    verdict = ("fără date" if c["diff_pct"] is None else
               "Consiliul a adus un plus față de reguli în această perioadă (nu e încă dovadă statistică)."
               if c["diff_pct"] > 0 else "Consiliul NU a adus un plus față de regulile simple în această perioadă.")
    return [verdict,
            (["Cont", f"Randament de la {c['from']}", "Scădere maximă"], [
                ["Contul unic (reguli + consiliu)", _fmt(c["unic_pct"], 2, "%"), _fmt(c["unic_dd"], 2, "%")],
                ["Reguli matematice (doar reguli, control)", _fmt(c["control_pct"], 2, "%"), _fmt(c["control_dd"], 2, "%")],
                ["Diferența (ce a adus consiliul)", _fmt(c["diff_pct"], 2, " puncte procentuale"), "—"],
            ]),
            f"{c['days']} zile comparate. Cost AI în aceeași perioadă: " + ("fără date" if cost is None else f"{cost:.2f} $ (total test)") +
            ". Contul de control a pornit după contul unic, deci comparația începe de la pornirea lui."]


def _vs_rule_blocks(v: dict | None) -> list:
    """Cât de des consiliul votează la fel ca regula simplă și ce au adus abaterile lui."""
    if not v or not v["comparable"]:
        return ["Încă nicio decizie încheiată în care regula simplă să fi avut semnal."]
    pct = lambda x: _fmt(None if x is None else 100 * x, 1, "%")
    return [
        v["verdict"],
        (["Situație", "Decizii", "Ce a adus"], [
            ["La fel ca regula", str(v["same"]), "—"],
            ["Sens opus regulii", str(v["opposite"]),
             f"consiliul a avut dreptate de {v['opposite_council_wins']} ori, regula de {v['opposite_rule_wins']} ori; "
             f"consiliul în medie {_fmt(v['opposite_council_mean_pct'], 2, '%')} / decizie"],
            ["Consiliul s-a abținut (regula avea semnal)", str(v["abstain"]),
             f"regula ar fi adus în medie {_fmt(v['abstain_rule_mean_pct'], 2, '%')} / decizie (negativ = pierdere evitată)"],
            ["Consiliul a votat, regula fără semnal", str(v["council_only_calls"]),
             f"în medie {_fmt(v['council_only_mean_pct'], 2, '%')} / decizie"],
        ]),
        f"Acord cu regula: {pct(v['agreement_rate'])} din {v['comparable']} decizii comparabile. "
        f"Valoarea abaterilor: {_fmt(v['differ_mean_pct'], 2, '%')} / decizie pe {v['differ_calls']} abateri "
        f"(p, testul semnului la sens opus: {_fmt(v['opposite_sign_test_p'], 3)}).",
    ]


def build(acc: dict, bench: dict | None, council: dict, cost: float | None, now: datetime,
          end: date = TEST_END, preliminary: bool = False, control: dict | None = None) -> list:
    """Secțiunile raportului ca (titlu, blocuri); un bloc e text sau tabel (antet, rânduri)."""
    ver = verdict(acc, bench, council)
    cur = acc["currency"]
    s = council["strategies"]
    sections = [
        ("Rezumat", [
            (f"Raport PRELIMINAR pe {TEST_START:%d.%m}–{end:%d.%m.%Y}; testul continuă până pe {TEST_END:%d.%m.%Y}, "
             "cu aceleași reguli și aceleași criterii. " if preliminary else
             f"Test oficial {TEST_START:%d.%m}–{end:%d.%m.%Y}. ") + f"Doar bani virtuali. Raport generat {now:%Y-%m-%d %H:%M} UTC.",
            (["Indicator", "Valoare"], [
                ["Capital inițial", f"{_fmt(acc['initial'])} {cur}"],
                ["Capital final", f"{_fmt(acc['final'])} {cur}"],
                ["Randament", _fmt(acc["return_pct"], 2, "%")],
                ["Scădere maximă (drawdown)", _fmt(acc["max_drawdown_pct"], 2, "%")],
                ["Zile cu rulare", str(acc["days"])],
                ["Cea mai bună / cea mai slabă zi", f"{_fmt(acc['best_day_pct'], 2, '%')} / {_fmt(acc['worst_day_pct'], 2, '%')}"],
                ["Execuții / comisioane", f"{acc['fills']} / {_fmt(acc['fees'])} {cur}"],
                ["Oprire de urgență (kill switch)", "da: " + str(acc["kill_reason"]) if acc["kill_switch"] else "nu"],
                ["S&P 500 „cumperi și ții”", "fără date" if bench is None else
                 f"{_fmt(bench['return_pct'], 2, '%')} ({bench['from']} → {bench['to']})"],
                ["Cost AI total", "fără date" if cost is None else f"{cost:.2f} $"],
            ]),
        ]),
        ("Verdict (criterii fixate pe 2.11.2026, înainte de rezultate)", [
            ver["text"],
            (["Criteriu", "Îndeplinit"], [[name, _mark(ok)] for name, ok in ver["checks"]]),
            f"p (testul semnului, hibrid): {_fmt(ver['sign_test_p'], 3)}",
        ]),
        ("Curba de capital (UTC, ultima rulare a zilei)", [
            (["Zi", f"Capital ({cur})"], [[d, _fmt(v)] for d, v in acc["curve"]]) if acc["curve"]
            else "Nicio rulare zilnică înregistrată.",
        ]),
        ("Consiliul AI: decizii încheiate la 5 zile", [
            council["note"] or f"{council['settled']} decizii încheiate.",
            (["Strategie", "Apeluri", "Rată reușită", "Randament mediu / apel"], [
                [label, str(s[k]["calls"]), _fmt(None if s[k]["hit_rate"] is None else 100 * s[k]["hit_rate"], 1, "%"),
                 _fmt(s[k]["mean_return_pct"], 2, "%")]
                for k, label in (("bot", "Doar reguli"), ("council", "Consiliul (majoritate)"),
                                 ("lean", "Înclinația consiliului"), ("hybrid", "Hibrid (consiliu + reguli de acord)"))]),
            (["Agent", "Apeluri", "Rată reușită", "Supra-încredere", "HOLD corect"], [
                [a, str(v["calls"]), _fmt(None if v["hit_rate"] is None else 100 * v["hit_rate"], 1, "%"),
                 _fmt(v["overconfidence"], 2), _fmt(None if v["hold_correct_rate"] is None else 100 * v["hold_correct_rate"], 1, "%")]
                for a, v in sorted(council["agents"].items())]) if council["agents"] else "Încă niciun agent cu decizii încheiate.",
        ]),
        ("Consiliul față de regula simplă (merită costul AI?)", _vs_rule_blocks(council.get("vs_rule"))),
        ("Consiliul AI (contul unic) față de Reguli matematice (contul de control)", _control_blocks(control, cost)),
        ("Poziții deschise la final", [
            (["Piață", "Cantitate", "Preț mediu"], [[p["symbol"], _fmt(p["quantity"], 4), _fmt(p["avg_price"], 4)]
                                                  for p in acc["positions"]]) if acc["positions"] else "Nicio poziție deschisă.",
        ]),
        ("Limite", [
            "Câteva săptămâni sunt prea puține pentru o concluzie statistică; deciziile pe piețe diferite sunt corelate.",
            "Rezultatele sunt pe bani virtuali, cu comisioane și alunecare estimate, nu reale.",
            "Criteriile verdictului au fost fixate înainte de rezultate și nu se ajustează după.",
        ]),
    ]
    return sections


def to_markdown(title: str, sections: list) -> str:
    out = [f"# {title}", ""]
    for head, blocks in sections:
        out += [f"## {head}", ""]
        for b in blocks:
            if isinstance(b, tuple):
                cols, rows = b
                out += ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
                out += ["| " + " | ".join(r) + " |" for r in rows]
            else:
                out.append(b)
            out.append("")
    return "\n".join(out)


def to_html(title: str, sections: list) -> str:
    e = html.escape
    out = [f"<html><head><meta charset='utf-8'><title>{e(title)}</title></head><body><h1>{e(title)}</h1>"]
    for head, blocks in sections:
        out.append(f"<h2>{e(head)}</h2>")
        for b in blocks:
            if isinstance(b, tuple):
                cols, rows = b
                out.append("<table border='1' cellpadding='4' style='border-collapse:collapse'><tr>"
                           + "".join(f"<th>{e(c)}</th>" for c in cols) + "</tr>"
                           + "".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in r) + "</tr>" for r in rows)
                           + "</table>")
            else:
                out.append(f"<p>{e(b)}</p>")
    out.append("</body></html>")
    return "".join(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--unic", required=True, help="paper.sqlite al contului unic")
    p.add_argument("--registry", required=True, help="registry.sqlite al consiliului")
    p.add_argument("--costs", help="costs.sqlite (opțional)")
    p.add_argument("--control", help="paper.sqlite al contului de control, doar reguli (opțional)")
    p.add_argument("--benchmark", help="CSV zilnic S&P 500 (opțional)")
    p.add_argument("--preliminar", action="store_true", help="raportul intermediar din 17.11 (fereastra 31.10–16.11)")
    p.add_argument("--end", default=None, help="ultima zi a ferestrei (implicit 2026-11-30, sau 2026-11-16 cu --preliminar)")
    p.add_argument("--out", required=True, help="prefixul fișierelor (.md și .html)")
    args = p.parse_args(argv)
    try:
        acc = account(args.unic)
        council = council_analytics.analyse(args.registry)
        ctrl = account(args.control) if args.control and Path(args.control).exists() else None
    except (sqlite3.Error, OSError, KeyError, ValueError) as exc:
        print(f"Raportul nu se poate genera: {exc}", file=sys.stderr)
        return 1
    end = date.fromisoformat(args.end) if args.end else (PRELIMINARY_END if args.preliminar else TEST_END)
    bench = benchmark(args.benchmark, TEST_START, end) if args.benchmark else None
    sections = build(acc, bench, council, ai_cost(args.costs), datetime.now(timezone.utc), end, args.preliminar,
                     control_comparison(acc, ctrl))
    title = ("Raport preliminar" if args.preliminar else "Raport final") + ": testul oficial BND (paper trading)"
    Path(f"{args.out}.md").write_text(to_markdown(title, sections), encoding="utf-8")
    Path(f"{args.out}.html").write_text(to_html(title, sections), encoding="utf-8")
    print(f"Scris {args.out}.md și {args.out}.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
