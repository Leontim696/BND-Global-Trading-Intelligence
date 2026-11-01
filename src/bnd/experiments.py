"""Registrul unic de experimente (AI Research Memory).

Fiecare experiment se înregistrează ÎNAINTE de rulare (ipoteză, parametri, date,
perioade, criteriu de acceptare) și se încheie după rulare (rezultat, cost,
verdict, concluzie). Registrul e un jurnal cu lanț de hash-uri (vezi
``audit_log``): nimic nu se șterge sau rescrie pe ascuns, iar eșecurile rămân.

Reguli aplicate de cod, nu doar scrise:
- fără informație din viitor: perioada de test începe după sfârșitul celei de
  antrenare, iar datele nu pot fi mai noi decât ``info_pana_la``;
- fără duplicate: aceeași ipoteză, tip, parametri, date și perioade au aceeași
  amprentă, deci o a doua rulare cere o justificare explicită;
- fără câștigători întâmplători: la verdictul „acceptat” cu valoare p, pragul se
  împarte la numărul de experimente din aceeași familie (corecție Bonferroni);
- criteriul de acceptare se scrie înainte, nu după ce se vede rezultatul.

    python -m src.bnd.experiments propune --titlu ... --ipoteza ... --familie capital \
        --tip backtest --criteriu "..." --antrenare 2015-01-01:2019-12-31 --test 2020-01-01:2024-12-31
    python -m src.bnd.experiments rezultat E-001 --verdict respins --concluzie "..."
    python -m src.bnd.experiments cauta volatilitate
    python -m src.bnd.experiments raport
"""

import argparse
import hashlib
import json
import math
import subprocess
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from . import audit_log
from .audit_log import fcntl

DEFAULT_PATH = Path("experimente/registru.jsonl")
VERDICTS = ("acceptat", "respins", "neconcludent")
ALPHA = 0.05


JUSTIFIED_TYPES = ("simulare", "control")      # singurele fără test statistic unic: acceptat fără p cu justificare


class RegistryError(ValueError):
    """Încălcarea unei reguli a registrului."""


@contextmanager
def _locked(path):
    """Blocare pe registru pentru tot ciclul citire–validare–adăugare (două procese nu pot lua același id)."""
    lock = Path(str(path) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+") as handle:
        if fcntl:
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _intact(path):
    """Un registru stricat (rând modificat/lipsă) oprește orice scriere: altfel ids și rezultate se pot încurca."""
    ok, message = audit_log.verify(path, allow_missing=True)
    if not ok:
        raise RegistryError(f"registrul nu trece verificarea ({message}); repară-l înainte de a scrie")


def _events(path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _day(text: str, field: str) -> date:
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        raise RegistryError(f"{field}: dată invalidă „{text}” (format AAAA-LL-ZZ)") from None


def _period(text: str | None, field: str):
    if not text:
        return None
    try:
        start, end = text.split(":")
    except ValueError:
        raise RegistryError(f"{field}: folosește AAAA-LL-ZZ:AAAA-LL-ZZ") from None
    a, b = _day(start, field), _day(end, field)
    if a > b:
        raise RegistryError(f"{field}: începutul e după sfârșit")
    return a, b


def file_hash(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprint(tip, ipoteza, parametri, date_hash, antrenare, test) -> str:
    body = json.dumps([tip, " ".join(ipoteza.lower().split()), parametri, date_hash,
                       antrenare, test], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _git_head() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, timeout=10, check=False)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def code_state() -> dict:
    """Codul exact: commit complet și dacă există modificări necomise în fișierele urmărite (None = necunoscut)."""
    def run(*args):
        out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=20, check=False)  # nosec B607
        return out.stdout.strip() if out.returncode == 0 else None
    try:
        commit = run("rev-parse", "HEAD")
        status = run("status", "--porcelain", "--untracked-files=no")
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "modificat": None}
    return {"commit": commit, "modificat": None if status is None else bool(status)}


def data_manifest(folder, names=None) -> dict:
    """Amprenta datelor folosite: hash, număr de rânduri și prima/ultima zi pentru fiecare CSV + un hash comun."""
    folder = Path(folder)
    files = [folder / f"{n}.csv" for n in names] if names else sorted(folder.glob("*.csv"))
    out = {}
    for path in files:
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        body = [x for x in lines[1:] if x.strip()]
        out[path.name] = {"sha256": file_hash(path), "randuri": len(body),
                          "prima": body[0].split(",")[0] if body else None,
                          "ultima": body[-1].split(",")[0] if body else None}
    combined = hashlib.sha256(json.dumps({k: v["sha256"] for k, v in out.items()}, sort_keys=True).encode()).hexdigest()
    return {"fisiere": out, "hash": combined[:16]}


COST_KEYS = ("cost_bps", "costuri", "costs")


def reproducibility(path=DEFAULT_PATH) -> list[dict]:
    """Pentru fiecare experiment: ce lipsește ca să poată fi repetat cu același cod, aceleași date, aceleași costuri și criterii."""
    out = []
    for e in experiments(path).values():
        problems, info = [], []
        result = e.get("rezultat") or {}
        repro = (result.get("metrici") or {}).get("reproducere") or {}
        simulated = e["tip"] in JUSTIFIED_TYPES
        if not e.get("criteriu", "").strip():
            problems.append("criteriul de acceptare lipsește")
        if not e.get("cod"):
            problems.append("codul de la propunere nu e înregistrat")
        after = result.get("cod_la_rezultat") or {}
        if result and not after.get("commit"):
            problems.append("codul de la rezultat nu e înregistrat (nu se poate dovedi că rularea a folosit același cod)")
        elif result and after.get("commit") and not str(after["commit"]).startswith(str(e.get("cod") or "?")):
            problems.append(f"codul s-a schimbat între propunere ({e.get('cod')}) și rezultat ({str(after['commit'])[:7]})")
        if after.get("modificat"):
            problems.append("rezultatul vine dintr-un cod cu modificări necomise")
        if simulated:
            if result and not repro.get("seeds"):
                problems.append("seed-urile simulării nu sunt înregistrate (sunt doar în cod)")
        elif not e.get("date") and not (repro.get("date") or {}).get("hash"):
            problems.append("datele nu sunt fixate prin hash (există doar eticheta: " + str(e.get("date_eticheta")) + ")")
        if not any(k in (e.get("parametri") or {}) for k in COST_KEYS):
            info.append("costurile nu sunt în parametri: vin din cod (CLASS_COSTS), fixate doar prin commit")
        out.append({"id": e["id"], "titlu": e["titlu"], "reproductibil": not problems,
                    "probleme": problems, "informatii": info})
    return out


def verify_data(path, id, folder) -> list[str]:
    """Compară datele de acum cu amprenta înregistrată la rezultat; listă de diferențe (goală = identice)."""
    e = experiments(path).get(id)
    if e is None:
        raise RegistryError(f"{id} nu există în registru")
    saved = (((e.get("rezultat") or {}).get("metrici") or {}).get("reproducere") or {}).get("date")
    if not saved:
        return [f"{id} nu are amprenta datelor înregistrată; nu se poate verifica"]
    now = data_manifest(folder, list(n[:-4] for n in saved["fisiere"]))
    diffs = []
    for name, info in saved["fisiere"].items():
        cur = now["fisiere"].get(name)
        if cur is None:
            diffs.append(f"{name}: lipsește")
        elif cur["sha256"] != info["sha256"]:
            diffs.append(f"{name}: conținut diferit ({info['randuri']} -> {cur['randuri']} rânduri)")
    return diffs


def experiments(path=DEFAULT_PATH) -> dict:
    """id -> starea curentă (propunere + rezultat, dacă există)."""
    state = {}
    for row in _events(path):
        data = row.get("data", {})
        if row.get("kind") == "experiment_propus":
            state[data["id"]] = {**data, "stare": "propus", "propus_la": row["time"]}
        elif row.get("kind") == "experiment_nota" and data.get("id") in state:
            state[data["id"]].setdefault("note", []).append({"time": row["time"], "text": data["text"]})
        elif row.get("kind") == "experiment_rezultat" and data.get("id") in state:
            state[data["id"]].update({"stare": "încheiat", "rezultat": data,
                                      "incheiat_la": row["time"]})
    return state


def family_count(state: dict, familie: str) -> int:
    return sum(1 for e in state.values() if e["familie"] == familie)


def propose(path=DEFAULT_PATH, *, titlu, ipoteza, familie, tip, criteriu, parametri=None,
            date_fisiere=(), date_eticheta=None, antrenare=None, test=None, info_pana_la=None,
            cost_estimat_usd=0.0, justificare_duplicat=None, now=None) -> dict:
    for field, value in (("titlu", titlu), ("ipoteza", ipoteza), ("familie", familie),
                         ("tip", tip), ("criteriu", criteriu)):
        if not (value or "").strip():
            raise RegistryError(f"{field} e obligatoriu (criteriul se scrie înainte de rulare)")
    train, tested = _period(antrenare, "antrenare"), _period(test, "test")
    if train and tested and tested[0] <= train[1]:
        raise RegistryError("perioada de test trebuie să înceapă după sfârșitul celei de "
                            "antrenare (altfel se folosește informație din viitor)")
    limit = _day(info_pana_la, "info_pana_la") if info_pana_la else None
    if limit and tested and tested[1] > limit:
        raise RegistryError("perioada de test depășește data până la care informația era "
                            "disponibilă (info_pana_la)")
    with _locked(path):
        return _propose_locked(path, titlu, ipoteza, familie, tip, criteriu, parametri, date_fisiere, date_eticheta,
                               train, tested, antrenare, test, info_pana_la, cost_estimat_usd,
                               justificare_duplicat, now)


def _propose_locked(path, titlu, ipoteza, familie, tip, criteriu, parametri, date_fisiere, date_eticheta,
                    train, tested, antrenare, test, info_pana_la, cost_estimat_usd, justificare_duplicat, now):
    _intact(path)
    hashes = {str(p): file_hash(p) for p in date_fisiere}
    date_hash = hashlib.sha256(json.dumps(hashes or date_eticheta, sort_keys=True).encode()).hexdigest()[:16]
    key = fingerprint(tip, ipoteza, parametri or {}, date_hash, antrenare, test)
    state = experiments(path)
    twin = next((e["id"] for e in state.values() if e["amprenta"] == key), None)
    if twin and not (justificare_duplicat or "").strip():
        raise RegistryError(f"duplicat al {twin} (aceeași amprentă {key}); "
                            "adaugă --justificare-duplicat dacă repetarea e intenționată")
    next_number = 1 + max((int(i.split("-")[1]) for i in state if i.startswith("E-")), default=0)
    entry = {"id": f"E-{next_number:03d}", "titlu": titlu.strip(), "ipoteza": ipoteza.strip(),
             "familie": familie.strip(), "tip": tip, "criteriu": criteriu.strip(),
             "parametri": parametri or {}, "date": hashes, "date_eticheta": date_eticheta,
             "antrenare": antrenare, "test": test, "info_pana_la": info_pana_la,
             "cost_estimat_usd": cost_estimat_usd, "amprenta": key, "cod": _git_head(),
             "duplicat_al": twin, "justificare_duplicat": justificare_duplicat,
             "numar_in_familie": family_count(state, familie.strip()) + 1}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    audit_log.append(path, "experiment_propus", entry, now)
    return entry


def finish(path=DEFAULT_PATH, *, id, verdict, concluzie, metrici=None, cost_usd=0.0,
           p_valoare=None, justificare_fara_p=None, now=None) -> dict:
    metrici = dict(metrici or {})
    if verdict not in VERDICTS:
        raise RegistryError(f"verdict: unul dintre {', '.join(VERDICTS)}")
    if not (concluzie or "").strip():
        raise RegistryError("concluzia e obligatorie, inclusiv pentru eșecuri")
    if p_valoare is not None and not (isinstance(p_valoare, (int, float)) and math.isfinite(p_valoare)
                                      and 0 <= p_valoare <= 1):
        raise RegistryError(f"valoarea p trebuie să fie un număr între 0 și 1 (primit: {p_valoare})")
    with _locked(path):
        _intact(path)
        state = experiments(path)
        if id not in state:
            raise RegistryError(f"{id} nu există în registru")
        if state[id]["stare"] == "încheiat":
            raise RegistryError(f"{id} e deja încheiat (rezultatele nu se rescriu; propune un nou experiment)")
        tests = family_count(state, state[id]["familie"])
        threshold = ALPHA / tests
        if verdict == "acceptat" and p_valoare is None:
            if state[id]["tip"] not in JUSTIFIED_TYPES:
                raise RegistryError(f"„acceptat” cere valoarea p pentru un experiment de tip „{state[id]['tip']}”; "
                                    f"fără p se acceptă doar tipurile: {', '.join(JUSTIFIED_TYPES)}")
            if not (justificare_fara_p or "").strip():
                raise RegistryError("„acceptat” fără p cere --justificare-fara-p cu motivul")
        if verdict == "acceptat" and p_valoare is not None and p_valoare > threshold:
            raise RegistryError(
                f"nu se poate accepta: p={p_valoare} > {threshold:.4f} (= {ALPHA}/{tests} experimente "
                f"în familia „{state[id]['familie']}”). Marchează „neconcludent” sau „respins”.")
        row = {"id": id, "verdict": verdict, "concluzie": concluzie.strip(), "metrici": metrici,
               "cost_usd": cost_usd, "p_valoare": p_valoare, "prag_corectat": threshold,
               "justificare_fara_p": justificare_fara_p, "experimente_in_familie": tests,
               "cod_la_rezultat": code_state()}
        audit_log.append(path, "experiment_rezultat", row, now)
    return row


def add_note(path=DEFAULT_PATH, *, id, text, now=None) -> dict:
    """Interpretare adăugată ulterior; rezultatul și verdictul rămân neschimbate."""
    if not (text or "").strip():
        raise RegistryError("nota nu poate fi goală")
    with _locked(path):
        _intact(path)
        if id not in experiments(path):
            raise RegistryError(f"{id} nu există în registru")
        return audit_log.append(path, "experiment_nota", {"id": id, "text": text.strip()}, now)


def search(path, text: str) -> list[dict]:
    words = [w for w in text.lower().split() if w]
    found = []
    for e in experiments(path).values():
        haystack = " ".join([e["titlu"], e["ipoteza"], e["familie"], e["tip"],
                             e.get("rezultat", {}).get("concluzie", "")]
                            + [n["text"] for n in e.get("note", [])]).lower()
        if all(w in haystack for w in words):
            found.append(e)
    return found


def report(path=DEFAULT_PATH) -> str:
    state = experiments(path)
    ok, message = audit_log.verify(path, allow_missing=True)
    lines = ["# Registrul de experimente", "", f"Integritate: {'corect' if ok else 'STRICAT'} — {message}", ""]
    if not state:
        return "\n".join(lines + ["Niciun experiment înregistrat încă."])
    counts = {}
    for e in state.values():
        verdict = e.get("rezultat", {}).get("verdict", "în curs")
        counts[verdict] = counts.get(verdict, 0) + 1
    lines.append("Total: " + ", ".join(f"{n} {v}" for v, n in sorted(counts.items())))
    lines.append(f"Cost cumulat: {sum(e.get('rezultat', {}).get('cost_usd', 0) for e in state.values()):.2f} $")
    lines += ["", "| ID | Familie | Titlu | Stare | Verdict |", "|---|---|---|---|---|"]
    for e in state.values():
        verdict = e.get("rezultat", {}).get("verdict", "–")
        lines.append(f"| {e['id']} | {e['familie']} | {e['titlu']} | {e['stare']} | {verdict} |")
    lines.append("")
    for e in state.values():
        if "rezultat" in e:
            lines += [f"### {e['id']} — {e['titlu']}", f"- Ipoteză: {e['ipoteza']}",
                      f"- Criteriu (scris înainte): {e['criteriu']}",
                      f"- Verdict: **{e['rezultat']['verdict']}** — {e['rezultat']['concluzie']}"]
            lines += [f"- Notă ({n['time'][:10]}): {n['text']}" for n in e.get("note", [])] + [""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="experiments")
    parser.add_argument("--registru", default=str(DEFAULT_PATH))
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("propune")
    for name in ("titlu", "ipoteza", "familie", "tip", "criteriu"):
        p.add_argument(f"--{name}", required=True)
    p.add_argument("--parametri", default="{}", help="JSON")
    p.add_argument("--date", nargs="*", default=[])
    p.add_argument("--date-eticheta")
    p.add_argument("--antrenare")
    p.add_argument("--test")
    p.add_argument("--info-pana-la")
    p.add_argument("--cost-estimat", type=float, default=0.0)
    p.add_argument("--justificare-duplicat")
    r = sub.add_parser("rezultat")
    r.add_argument("id")
    r.add_argument("--verdict", required=True)
    r.add_argument("--concluzie", required=True)
    r.add_argument("--metrici", default="{}", help="JSON")
    r.add_argument("--cost", type=float, default=0.0)
    r.add_argument("--p", type=float)
    r.add_argument("--justificare-fara-p", help="obligatoriu pentru „acceptat” fără valoare p")
    c = sub.add_parser("cauta")
    c.add_argument("text", nargs="+")
    n = sub.add_parser("nota")
    n.add_argument("id")
    n.add_argument("text")
    sub.add_parser("raport")
    rp = sub.add_parser("reproducere", help="ce lipsește ca fiecare experiment să poată fi repetat (cod, date, costuri, criterii)")
    rp.add_argument("id", nargs="?")
    vd = sub.add_parser("verifica-date", help="compară un folder de date cu amprenta înregistrată la rezultat")
    vd.add_argument("id")
    vd.add_argument("folder")
    sub.add_parser("verifica")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "propune":
            entry = propose(args.registru, titlu=args.titlu, ipoteza=args.ipoteza,
                            familie=args.familie, tip=args.tip, criteriu=args.criteriu,
                            parametri=json.loads(args.parametri), date_fisiere=args.date,
                            date_eticheta=args.date_eticheta, antrenare=args.antrenare,
                            test=args.test, info_pana_la=args.info_pana_la,
                            cost_estimat_usd=args.cost_estimat,
                            justificare_duplicat=args.justificare_duplicat)
            print(f"Înregistrat {entry['id']} (amprenta {entry['amprenta']}, "
                  f"al {entry['numar_in_familie']}-lea din familie).")
        elif args.cmd == "rezultat":
            row = finish(args.registru, id=args.id, verdict=args.verdict,
                                     concluzie=args.concluzie, metrici=json.loads(args.metrici),
                                     cost_usd=args.cost, p_valoare=args.p,
                         justificare_fara_p=args.justificare_fara_p)
            print(f"Încheiat {row['id']}: {row['verdict']}.")
        elif args.cmd == "nota":
            add_note(args.registru, id=args.id, text=args.text)
            print(f"Notă adăugată la {args.id}.")
        elif args.cmd == "cauta":
            for e in search(args.registru, " ".join(args.text)):
                verdict = e.get("rezultat", {}).get("verdict", "în curs")
                print(f"{e['id']} [{e['familie']}] {e['titlu']} — {verdict}")
        elif args.cmd == "reproducere":
            rows = [r for r in reproducibility(args.registru) if not args.id or r["id"] == args.id]
            for r in rows:
                print(f"{r['id']} {'REPRODUCTIBIL' if r['reproductibil'] else 'NEREPRODUCTIBIL COMPLET'} — {r['titlu']}")
                for item in r["probleme"]:
                    print("   - " + item)
                for item in r["informatii"]:
                    print("   · " + item)
            return 0 if all(r["reproductibil"] for r in rows) else 1
        elif args.cmd == "verifica-date":
            diffs = verify_data(args.registru, args.id, args.folder)
            print("\n".join(diffs) if diffs else "Datele sunt identice cu cele din rezultat.")
            return 1 if diffs else 0
        elif args.cmd == "verifica":
            ok, message = audit_log.verify(args.registru, allow_missing=False)
            print(message)
            return 0 if ok else 1
        else:
            print(report(args.registru))
    except (RegistryError, ValueError) as exc:
        print("Eroare:", exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
