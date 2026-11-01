"""Raport de expuneri corelate (Portfolio Brain, pasul 1): doar citire, nu schimbă nicio poziție.

Pozițiile care se mișcă împreună sunt, de fapt, același risc: BTC, ETH și Nasdaq pot fi trei
poziții pe hârtie, dar un singur pariu. Raportul pornește din greutățile pozițiilor (fracțiuni
din capital, cu semn: long +, short −) și din prețurile ultimelor zile, și arată:

- clustere: grupuri de piețe ale căror PROFIT/PIERDERE se mișcă împreună (corelația rândurilor
  ajustată cu direcția: un long și un short pe active corelate se compensează, nu se adună);
- pentru fiecare cluster: expunerea netă și brută, volatilitatea zilnică a clusterului în % din
  capital și partea din riscul total al portofoliului (contribuție Euler, suma = 100%);
- avertismente când un cluster trece pragul de expunere brută sau de risc.

Corelațiile se calculează pe zilele comune tuturor pozițiilor din ultima fereastră (fără informație
din viitor: doar preț istoric). Nu e o prognoză și nu e un ordin.

    python -m src.bnd.exposure --state paper.sqlite --data-dir data --out expuneri.json
"""

import argparse
import json
import sys
from math import sqrt
from pathlib import Path

WINDOW = 60                  # zile de randamente
MIN_OBS = 20                 # sub atâtea randamente comune, nu se calculează
CLUSTER_CORR = 0.70          # corelație (ajustată cu direcția) de la care două poziții sunt „același risc”
WARN_GROSS = 0.40            # cluster cu expunere brută peste 40% din capital
WARN_RISK_SHARE = 0.50       # sau peste 50% din riscul portofoliului (cu cel puțin 2 poziții)


def _returns(closes: dict, window: int):
    """symbol -> randamente pe zilele comune tuturor, ultimele `window` (None dacă prea puține)."""
    common = None
    for series in closes.values():
        dates = set(series)
        common = dates if common is None else common & dates
    days = sorted(common or [])[-(window + 1):]
    if len(days) < MIN_OBS + 1:
        return None, len(days) - 1
    return ({s: [closes[s][b] / closes[s][a] - 1 for a, b in zip(days, days[1:])] for s in closes},
            len(days) - 1)


def _cov(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (len(a) - 1)


def _clusters(symbols, corr, weights):
    parent = {s: s for s in symbols}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(symbols):
        for b in symbols[i + 1:]:
            sign = (weights[a] > 0) - (weights[a] < 0)
            other = (weights[b] > 0) - (weights[b] < 0)
            if corr[a][b] * sign * other >= CLUSTER_CORR:
                parent[find(a)] = find(b)
    groups = {}
    for s in symbols:
        groups.setdefault(find(s), []).append(s)
    return list(groups.values())


def analyse(weights: dict, closes: dict, window: int = WINDOW) -> dict:
    """weights: simbol -> fracție din capital cu semn; closes: simbol -> {dată: închidere}."""
    held = {s: w for s, w in weights.items() if abs(w) > 1e-9}
    missing = sorted(s for s in held if len(closes.get(s, {})) < 2)
    used = {s: w for s, w in held.items() if s not in missing}
    base = {"window_days": window, "missing_data": missing,
            "gross": sum(abs(w) for w in held.values()), "net": sum(held.values()),
            "positions": len(held), "clusters": [], "warnings": [], "portfolio_vol_daily_pct": None}
    if not used:
        return {**base, "note": "Nicio poziție de analizat." if not held else "Fără istoric de preț."}
    rets, obs = _returns({s: closes[s] for s in used}, window)
    if rets is None:
        return {**base, "observations": max(obs, 0),
                "note": f"Prea puține zile comune ({max(obs, 0)}, minim {MIN_OBS}) pentru corelații."}
    symbols = sorted(used)
    cov = {a: {b: _cov(rets[a], rets[b]) for b in symbols} for a in symbols}
    corr = {a: {b: (cov[a][b] / sqrt(cov[a][a] * cov[b][b]) if cov[a][a] > 0 and cov[b][b] > 0 else 0.0)
                for b in symbols} for a in symbols}
    # Σw pentru fiecare simbol; riscul portofoliului = sqrt(Σ w·(Σw)).
    sigma_w = {a: sum(cov[a][b] * used[b] for b in symbols) for a in symbols}
    variance = sum(used[a] * sigma_w[a] for a in symbols)
    total_vol = sqrt(variance) if variance > 0 else 0.0
    clusters = []
    for members in _clusters(symbols, corr, used):
        members.sort(key=lambda s: -abs(used[s]))
        contrib = sum(used[a] * sigma_w[a] for a in members)
        var_c = sum(used[a] * used[b] * cov[a][b] for a in members for b in members)
        clusters.append({
            "members": members, "net": sum(used[a] for a in members),
            "gross": sum(abs(used[a]) for a in members),
            "vol_daily_pct": 100 * sqrt(max(var_c, 0.0)),
            "risk_share": contrib / variance if variance > 0 else None,
            "avg_corr": (sum(abs(corr[a][b]) for a in members for b in members if a < b)
                         / max(1, len(members) * (len(members) - 1) // 2)) if len(members) > 1 else None})
    clusters.sort(key=lambda c: -(c["risk_share"] or 0))
    warnings = []
    for c in clusters:
        label = ", ".join(c["members"][:4]) + ("…" if len(c["members"]) > 4 else "")
        if len(c["members"]) >= 2 and c["gross"] >= WARN_GROSS:
            warnings.append(f"Grup corelat ({label}): {100 * c['gross']:.0f}% din capital în piețe care se mișcă împreună.")
        if len(c["members"]) >= 2 and (c["risk_share"] or 0) >= WARN_RISK_SHARE:
            warnings.append(f"Grup corelat ({label}): {100 * c['risk_share']:.0f}% din riscul portofoliului.")
    hedges = [{"a": a, "b": b, "corr": corr[a][b]} for i, a in enumerate(symbols) for b in symbols[i + 1:]
              if corr[a][b] * ((used[a] > 0) - (used[a] < 0)) * ((used[b] > 0) - (used[b] < 0)) <= -CLUSTER_CORR]
    return {**base, "observations": obs, "clusters": clusters, "warnings": warnings, "hedges": hedges,
            "portfolio_vol_daily_pct": 100 * total_vol,
            "diversification": (sum(abs(used[a]) * sqrt(cov[a][a]) for a in symbols) / total_vol
                                if total_vol > 0 else None)}


def closes_from_folder(folder, symbols) -> dict:
    from .market_data import load_csv
    out = {}
    for s in symbols:
        path = Path(folder) / f"{s}.csv"
        if path.exists():
            out[s] = {c.open_time.date(): c.close for c in load_csv(path)}
    return out


def from_account(state, data_dir, window: int = WINDOW) -> dict:
    """Expunerile curente (poziții deschise) și cele planificate (greutățile ultimei rulări)."""
    from .paper_engine import PaperEngine
    engine = PaperEngine.open(state)
    try:
        equity = engine.summary()["equity"]
        current = {}
        for p in engine.positions():
            mark = engine.mark(p["symbol"])
            price = mark["price"] if mark else p["avg_price"]
            current[p["symbol"]] = p["quantity"] * price / equity if equity else 0.0
        runs = engine.journal("daily_run")
        planned = dict(runs[-1]["payload"].get("weights", {})) if runs else {}
    finally:
        engine.close()
    closes = closes_from_folder(data_dir, set(current) | set(planned))
    return {"current": analyse(current, closes, window), "planned": analyse(planned, closes, window)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="exposure")
    parser.add_argument("--state", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--window", type=int, default=WINDOW)
    args = parser.parse_args(argv)
    try:
        report = from_account(args.state, args.data_dir, args.window)
    except Exception as exc:       # raport opțional: nu strică rularea zilnică
        print("Avertisment:", exc, file=sys.stderr)
        report = {"error": str(exc)}
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
