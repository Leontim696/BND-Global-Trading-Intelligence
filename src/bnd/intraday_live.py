"""Execuție intraday la 10 minute (cerută de proprietar pe 5.11.2026), bani virtuali, fără apeluri AI.

Trei conturi paralele, separate de contul oficial (care rămâne neschimbat până pe 30.11):

    P26  geamănul lui P24 la 10 minute: aceleași ponderi țintă ca P24 (calculate o dată pe zi din voturi + regulă),
         aceleași limite, take profit +7% / stop −2%, reciclare și pauză de o zi; diferența e DOAR că intrările,
         take profit-ul și stop-ul se verifică pe lumânări de 5 minute, la fiecare 10 minute, nu pe lumânarea zilnică.
         Arată direct cât contează frecvența execuției.
    P27  trend pe crypto, lumânări de 15 minute (EMA 20/80 + impuls pe 4 ore), stop −3%.
    P28  revenire la medie pe crypto, lumânări de 5 minute (abatere ≥ 2,5σ față de media pe 3 ore), stop −2%.

P27 și P28 sunt reguli fixe, decise dinainte (E-017 și E-018 în experimente/registru.jsonl) și testate pe istoric
înainte de pornire. Ce se schimbă după rezultate se decide de proprietar, nu din mers.

Datele: crypto din API-ul public Binance (data-api.binance.vision), restul pieței din Yahoo Finance la 5 minute
(doar cât e bursa deschisă). Lumânările se păstrează pe ramura `intraday` (ultimele 3 zile), ca o singură descărcare
să servească toate conturile.

    python -m src.bnd.intraday_live cycle --dir st --p24 p24/paper.sqlite --daily-dir zilnic
    python -m src.bnd.intraday_live backtest --days 30 --out backtest.json
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from math import log, sqrt
from pathlib import Path
from statistics import mean, pstdev
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from . import paper_runner, recycling
from .market_data import (YAHOO_CHART_URL, Candle, MarketDataError, fetch_binance_klines, load_csv,
                          save_csv)
from .paper_engine import EngineLimits, PaperEngine
from .portfolio import PortfolioConfig
from .safety import trading_mode
from .universe import UNIVERSES

STEP = timedelta(minutes=5)
KEEP = timedelta(days=3)                 # cât istoric de 5 minute se păstrează pe ramură
CAPITAL = 11183.0
CRYPTO = ("crypto", "memecoin")

TWIN = "p26-p24-la-10-min"
TWIN_OF = "p24-tp7-sl2-reciclare"
TREND = "p27-trend-15m"
REVERT = "p28-revenire-5m"
ACCOUNTS = {
    TWIN: "Geamănul lui P24 la 10 minute (TP +7%, stop −2%, reciclare)",
    TREND: "Trend crypto pe 15 minute (EMA 20/80 + impuls 4h, stop −3%)",
    REVERT: "Revenire la medie crypto pe 5 minute (≥ 2,5σ față de media pe 3h, stop −2%)",
}

# Istoricul versiunilor (punctul 4 din auditul GPT, 5.11): ce s-a schimbat și de când, ca raportul final să știe exact
# ce configurație a produs fiecare rezultat. (versiune, activare UTC, ce s-a schimbat)
VERSIONS = {
    TWIN: [("v1", "2026-11-05T05:50Z", "pornire: istoric zilnic doar din date-piete (57 din 100 de piețe)"),
           ("v2", "2026-11-05T08:00Z", "istoric zilnic pentru toate cele 100 de piețe (scripts/date_zilnice_unic.sh) "
                                       "și diagnostic pe motive; înainte, 43 de piețe (acțiuni, apărare, unele valute "
                                       "și mărfuri) nu puteau primi ordine")],
    TREND: [("v1", "2026-11-05T05:50Z", "pornire")],
    REVERT: [("v1", "2026-11-05T05:50Z", "pornire")],
}

# P27/P28: cel mult 10 poziții a câte 10% din cont (expunere totală ≤ 1x), aceleași costuri ca în conturile zilnice.
MAX_POSITIONS = 10
POSITION_WEIGHT = 0.10
STRATEGY_STOP = {TREND: 3.0, REVERT: 2.0}

# Reguli P27 (pe lumânări de 15 minute)
EMA_FAST, EMA_SLOW, MOMENTUM_BARS, VOL_BARS = 20, 80, 16, 96
# Reguli P28 (pe lumânări de 5 minute)
MR_WINDOW, MR_ENTER, MR_EXIT, MR_MAX_BARS = 36, 2.5, 0.3, 24


# ---------------------------------------------------------------- date

def markets(crypto_only: bool = False):
    out = list(UNIVERSES["unic"])
    return [m for m in out if m.asset_class in CRYPTO] if crypto_only else out


def binance_pair(market) -> str | None:
    if market.asset_class not in CRYPTO:
        return None
    symbol = market.symbol.upper()
    if symbol.endswith("-USD"):
        return symbol[:-4] + "USDT"
    return symbol if symbol.endswith("USDT") else None


def parse_yahoo_intraday(payload, step: timedelta = STEP) -> list[Candle]:
    """Lumânări intraday dintr-un răspuns Yahoo chart (rândurile incomplete se sar)."""
    try:
        result = payload["chart"]["result"][0]
        stamps = result.get("timestamp") or []
        q = result["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise MarketDataError("Invalid Yahoo chart response") from exc
    seconds = int(step.total_seconds())
    by_time = {}
    for i, stamp in enumerate(stamps):
        try:
            o, h, l, c, v = (q[k][i] for k in ("open", "high", "low", "close", "volume"))
        except (KeyError, IndexError, TypeError):
            continue
        if None in (stamp, o, h, l, c) or min(o, h, l, c) <= 0:
            continue
        t = datetime.fromtimestamp(int(stamp) // seconds * seconds, tz=timezone.utc)
        by_time[t] = Candle(t, float(o), float(max(o, h, l, c)), float(min(o, h, l, c)), float(c), float(v or 0.0))
    return [by_time[t] for t in sorted(by_time)]


def fetch_yahoo_intraday(symbol: str, start: datetime, end: datetime, timeout: float = 20.0) -> list[Candle]:
    query = urlencode({"period1": int(start.timestamp()), "period2": int(end.timestamp()), "interval": "5m"})
    request = Request(YAHOO_CHART_URL + quote(symbol, safe="") + "?" + query,
                      headers={"User-Agent": "Mozilla/5.0 (BND research backtester)"}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:  # nosec B310 (URL constant fix, https)
            payload = json.loads(response.read(10_000_001))
    except HTTPError as exc:
        raise MarketDataError(f"Yahoo HTTP error for {symbol}: {exc.code}") from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise MarketDataError(f"Yahoo request failed for {symbol}") from exc
    return parse_yahoo_intraday(payload)


def fetch_bars(market, start: datetime, end: datetime) -> list[Candle]:
    """Lumânări de 5 minute ÎNCHEIATE cu open_time în [start, end)."""
    pair = binance_pair(market)
    if pair:
        candles = fetch_binance_klines(pair, "5m", start, end)
    else:
        candles = fetch_yahoo_intraday(market.symbol, start, end)
    return [c for c in candles if start <= c.open_time and c.open_time + STEP <= end]


def update_bars(folder: Path, chosen, now: datetime, fetch=fetch_bars) -> dict:
    """Completează bars/<PIAȚĂ>.csv cu lumânările noi; o piață care nu răspunde nu le oprește pe celelalte."""
    folder.mkdir(parents=True, exist_ok=True)
    out, errors = {}, {}
    for market in chosen:
        path = folder / f"{market.name}.csv"
        old = load_csv(path) if path.exists() else []
        start = max(old[-1].open_time + STEP, now - KEEP) if old else now - timedelta(hours=26)
        new = []
        if start + STEP <= now:
            try:
                new = fetch(market, start, now)
            except MarketDataError as exc:
                errors[market.name] = str(exc)[:120]
        merged = {c.open_time: c for c in old if c.open_time >= now - KEEP}
        merged.update({c.open_time: c for c in new})
        candles = [merged[t] for t in sorted(merged)]
        if candles:
            save_csv(candles, path)
            out[market.name] = candles
    return {"bars": out, "errors": errors}


def load_bars(folder: Path) -> dict:
    return {p.stem: load_csv(p) for p in sorted(Path(folder).glob("*.csv"))} if Path(folder).exists() else {}


# ---------------------------------------------------------------- reguli P27 / P28

def resample(candles, minutes: int = 15) -> list[Candle]:
    """Lumânări de `minutes` minute din cele de 5 minute; doar intervalele complete."""
    size = minutes // 5
    groups: dict = {}
    for c in candles:
        t = c.open_time
        key = t.replace(minute=t.minute - t.minute % minutes, second=0, microsecond=0)
        groups.setdefault(key, []).append(c)
    out = []
    for key in sorted(groups):
        g = groups[key]
        if len(g) == size:
            out.append(Candle(key, g[0].open, max(c.high for c in g), min(c.low for c in g), g[-1].close,
                              sum(c.volume for c in g)))
    return out


def _ema(values, span):
    k, out, cur = 2 / (span + 1), [], None
    for v in values:
        cur = v if cur is None else cur + k * (v - cur)
        out.append(cur)
    return out


def trend_series(candles15) -> list[tuple[int, float]]:
    """(direcție, putere) după fiecare lumânare de 15 minute; 0 până există destul istoric."""
    closes = [c.close for c in candles15]
    fast, slow = _ema(closes, EMA_FAST), _ema(closes, EMA_SLOW)
    out = []
    for i, c in enumerate(closes):
        if i < max(EMA_SLOW, VOL_BARS):
            out.append((0, 0.0))
            continue
        rets = [log(closes[j] / closes[j - 1]) for j in range(i - VOL_BARS + 1, i + 1)]
        vol = pstdev(rets)
        roc = c / closes[i - MOMENTUM_BARS] - 1
        if vol <= 0:
            out.append((0, 0.0))
        elif c > slow[i] and fast[i] > slow[i] and roc > 0:
            out.append((1, roc / vol))
        elif c < slow[i] and fast[i] < slow[i] and roc < 0:
            out.append((-1, -roc / vol))
        else:
            out.append((0, 0.0))
    return out


def revert_series(candles5) -> list[tuple[int, float]]:
    """(direcție, putere) după fiecare lumânare de 5 minute: intră contra unei abateri ≥ 2,5σ, iese când prețul
    revine aproape de medie (|z| < 0,3 pe partea intrării) sau după 2 ore."""
    closes = [c.close for c in candles5]
    out, side, held = [], 0, 0
    for i, c in enumerate(closes):
        if i < MR_WINDOW:
            out.append((0, 0.0))
            continue
        window = closes[i - MR_WINDOW + 1:i + 1]
        sd = pstdev(window)
        z = (c - mean(window)) / sd if sd > 0 else 0.0
        if side and (side * z >= -MR_EXIT or held >= MR_MAX_BARS):
            side, held = 0, 0
        if not side and abs(z) >= MR_ENTER:
            side, held = (-1 if z > 0 else 1), 0
        if side:
            held += 1
        out.append((side, abs(z) if side else 0.0))
    return out


def strategy_signal(kind: str, candles5) -> tuple[int, float]:
    series = trend_series(resample(candles5, 15)) if kind == TREND else revert_series(candles5)
    return series[-1] if series else (0, 0.0)


def pick(signals: dict) -> dict:
    """Cele mai puternice MAX_POSITIONS semnale, fiecare cu POSITION_WEIGHT."""
    active = sorted(((s, n) for n, (d, s) in signals.items() if d), reverse=True)[:MAX_POSITIONS]
    chosen = {n for _, n in active}
    return {n: (signals[n][0] * POSITION_WEIGHT if n in chosen else 0.0) for n in signals}


# ---------------------------------------------------------------- conturi

def _limits(settings: dict | None) -> EngineLimits:
    # Limita de volatilitate a portofoliului din motor e gândită pe randamente zilnice; pe lumânări de 5 minute
    # ar subestima riscul de ~17 ori, așa că e oprită (0). Ponderile P26 vin deja calibrate zilnic din P24.
    if settings is None:
        return EngineLimits(financing_pct_annual=5.0, max_sector_pct=100.0, max_portfolio_vol_pct=0.0)
    return EngineLimits(financing_pct_annual=settings["financing"], max_portfolio_vol_pct=0.0,
                        **({"max_sector_pct": settings["max_sector"]} if settings.get("max_sector") else {}))


def open_account(path: Path, settings: dict | None, now: datetime) -> PaperEngine:
    if path.exists():
        return PaperEngine.open(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = PaperEngine.create(path, CAPITAL, currency="USD", limits=_limits(settings), now=now)
    if settings is not None:
        engine.record("runner_settings", settings, now)
    return engine


def _daily_history(engine, now) -> list[float]:
    by_day = {}
    for entry in engine.journal("intraday_run"):
        p = entry["payload"]
        if p["time"][:10] < now.date().isoformat():
            by_day[p["time"][:10]] = p["equity"]
    return [by_day[d] for d in sorted(by_day)] + [engine.equity()]


def _prefix(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H%M")


FRESH = timedelta(minutes=20)


def _fresh(engine, names, now) -> set:
    """Piețele cu o lumânare de 5 minute recentă. La celelalte (bursa închisă, date lipsă) nu se trimit și nu se
    anulează ordine: ordinul rămas se execută la prima lumânare de după deschidere, ca în realitate."""
    out = set()
    for name in names:
        mark = engine.mark(name)
        if mark and datetime.fromisoformat(mark["time"]) >= now - FRESH:
            out.add(name)
    return out


EUROPE = ("DE", "PA", "MI", "ST", "OL")


def session(market) -> str:
    """Sesiunea de tranzacționare (aproximativă, doar pentru diagnostic): după clasă și sufixul Yahoo."""
    from .calendars import session_of
    suffix = market.symbol.rsplit(".", 1)[-1] if "." in market.symbol else ""
    if market.asset_class in CRYPTO:
        return "crypto"
    if market.symbol.endswith("=X"):
        return "forex"
    if suffix in EUROPE:
        return "xetra"                    # Frankfurt/Paris/Milano/Stockholm/Oslo: ~9:00–17:30 ora Europei Centrale
    if suffix == "L":
        return "lse"
    return session_of(market.name, market.asset_class)


def diagnose(engine, weights: dict, daily: dict, by_name: dict, now) -> dict:
    """Piețele cu țintă nenulă care NU pot primi ordin acum, pe motive: fără istoric zilnic, fără lumânări intraday,
    bursa închisă sau date vechi (bursa deschisă, dar ultima lumânare de 5 minute e mai veche de 20 de minute)."""
    from .calendars import is_open
    out = {"fara_istoric_zilnic": [], "fara_lumanari_intraday": [], "bursa_inchisa": [], "date_vechi": []}
    for name, w in sorted(weights.items()):
        if not w:
            continue
        mark = engine.mark(name)
        if name not in daily or len(daily[name]) <= paper_runner.RunnerConfig().atr_period:
            out["fara_istoric_zilnic"].append(name)
        elif mark is None:
            out["fara_lumanari_intraday"].append(name)
        elif datetime.fromisoformat(mark["time"]) < now - FRESH:
            market = by_name.get(name)
            out["bursa_inchisa" if market and not is_open(session(market), now) else "date_vechi"].append(name)
    return out


def twin_cycle(engine, settings: dict, p24_report: dict, daily: dict, bars: dict, chosen, now) -> dict:
    """Un pas al geamănului: lumânările noi de 5 minute (umpleri, TP, stop), apoi ordinele spre ținta lui P24."""
    config = paper_runner._config(settings)
    for m in chosen:
        engine.register_instrument(paper_runner.instrument_for(m, config.cost_mult))
    fed = paper_runner.feed_new_candles(engine, {k: v for k, v in bars.items() if v})
    account = engine.account()
    report = {"time": now.isoformat(), "account": TWIN, "candles_processed": fed,
              "kill_switch": bool(account["kill_switch"]), "target_from": p24_report.get("time"), "orders": []}
    if not account["kill_switch"]:
        base = p24_report.get("weights_base") or p24_report.get("weights") or {}
        signals = p24_report.get("signals") or {}
        weights = {m.name: float(base.get(m.name, 0.0)) for m in chosen}
        if config.recycle:
            rules = recycling.RecycleRules(mode=config.recycle, **(
                {"cooldown_days": config.recycle_cooldown} if config.recycle_cooldown is not None else {}))
            exits = recycling.recent_exits(engine.fills(), now, rules.cooldown_days)
            blocked = recycling.guard(_daily_history(engine, now), account["peak_equity"], rules)
            weights, report["recycling"] = recycling.adjust(
                weights, signals, {k: v for k, v in daily.items() if k in weights}, exits, rules,
                config.portfolio.max_weight, config.portfolio.max_leverage, blocked)
        weights = paper_runner.fit_limits(engine, weights, config.margin)
        live = _fresh(engine, weights, now)
        data = {k: daily[k] for k in weights if k in daily and k in live}
        report["weights"] = weights
        report["markets_open"] = len(data)
        report["diagnostic"] = diagnose(engine, weights, daily, {m.name: m for m in chosen}, now)
        report["orders"] = paper_runner.rebalance(engine, data, weights, config, now, order_prefix=_prefix(now))
    return _finish(engine, report, now)


def strategy_config(kind: str) -> paper_runner.RunnerConfig:
    return paper_runner.RunnerConfig(
        portfolio=PortfolioConfig(max_leverage=1.0, max_weight=POSITION_WEIGHT, rebalance_threshold=0.05),
        stop_pct=STRATEGY_STOP[kind])


def strategy_cycle(engine, kind: str, bars: dict, chosen, now) -> dict:
    for m in chosen:
        engine.register_instrument(paper_runner.instrument_for(m))
    data = {m.name: bars[m.name] for m in chosen if bars.get(m.name)}
    fed = paper_runner.feed_new_candles(engine, data)
    signals = {n: strategy_signal(kind, c) for n, c in data.items()}
    return _finish(engine, strategy_decide(engine, kind, signals, data, now, fed), now)


def strategy_decide(engine, kind: str, signals: dict, data: dict, now, fed: int = 0) -> dict:
    """Decizia P27/P28 dintr-un set de semnale: cele mai puternice 10, câte 10%, limitele motorului, ordine pentru
    următoarea lumânare. Aceeași funcție în cont (la 10 minute) și în testul pe istoric cu motor (E-017/E-018 v2)."""
    config = strategy_config(kind)
    account = engine.account()
    report = {"time": now.isoformat(), "account": kind, "candles_processed": fed,
              "kill_switch": bool(account["kill_switch"]), "orders": []}
    if not account["kill_switch"]:
        weights = paper_runner.fit_limits(engine, pick(signals), config.margin)
        report["signals"] = {n: s for n, s in signals.items() if s[0]}
        report["weights"] = {n: w for n, w in weights.items() if w}
        live = _fresh(engine, data, now)
        report["orders"] = paper_runner.rebalance(engine, {k: v for k, v in data.items() if k in live}, weights,
                                                  config, now, order_prefix=_prefix(now))
    return report


def _finish(engine, report, now) -> dict:
    s = engine.summary()
    report.update(equity=s["equity"], cash=s["cash"], gross_leverage=s["gross_leverage"],
                  positions=len(engine.positions()))
    engine.record("intraday_run", {"time": report["time"], "equity": s["equity"],
                                   "orders": len(report["orders"]), "candles": report["candles_processed"]}, now)
    return report


def p24_state(path: Path) -> tuple[dict | None, dict | None]:
    """Setările și ultimul raport zilnic al lui P24 (sursa țintelor pentru geamăn)."""
    if not path or not Path(path).exists():
        return None, None
    engine = PaperEngine.open(path)
    try:
        settings = engine.journal("runner_settings")
        runs = engine.journal("daily_run")
        return (settings[-1]["payload"] if settings else None), (runs[-1]["payload"] if runs else None)
    finally:
        engine.close()


def cycle(folder: Path, p24_path: Path | None, daily_dir: Path | None, now: datetime, fetch=fetch_bars) -> dict:
    trading_mode()
    folder = Path(folder)
    every = markets()
    crypto = markets(crypto_only=True)
    fetched = update_bars(folder / "bars", every, now, fetch)
    bars = fetched["bars"]
    status = {"time": now.isoformat(timespec="minutes"), "markets_with_bars": len(bars),
              "fetch_errors": fetched["errors"], "accounts": {}}
    daily = load_bars(daily_dir) if daily_dir else {}
    settings, p24_report = p24_state(p24_path)
    jobs = [(TREND, None), (REVERT, None)]
    if settings and p24_report:
        jobs.insert(0, (TWIN, settings))
    else:
        status["accounts"][TWIN] = {"error": "P24 nu are încă un raport zilnic"}
    for key, conf in jobs:
        try:
            engine = open_account(folder / key / "paper.sqlite", conf, now)
            try:
                report = (twin_cycle(engine, settings, p24_report, daily, bars, every, now) if key == TWIN
                          else strategy_cycle(engine, key, bars, crypto, now))
            finally:
                engine.close()
            (folder / key / "last_run.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
            status["accounts"][key] = {"equity": round(report["equity"], 2), "positions": report["positions"],
                                       "orders": len(report["orders"]), "kill_switch": report["kill_switch"],
                                       "version": VERSIONS[key][-1][0],
                                       **({"diagnostic": {k: len(v) for k, v in report["diagnostic"].items()}}
                                          if "diagnostic" in report else {})}
        except Exception as exc:          # un cont stricat nu le oprește pe celelalte
            status["accounts"][key] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    (folder / "status.json").write_text(json.dumps(status, indent=1, ensure_ascii=False), encoding="utf-8")
    return status


# ---------------------------------------------------------------- test pe istoric (E-017 / E-018)

def backtest_market(kind: str, candles5, cost_pct: float) -> dict:
    """Randamentul unei piețe pe bara de 5 minute: poziția decisă la închiderea barei t se ține până la t+1;
    fiecare schimbare de poziție plătește costul (comision + alunecare) pe partea schimbată. Fără stop (simplificare,
    notată în raport)."""
    if kind == TREND:
        c15 = resample(candles5, 15)
        by_time = {c.open_time: s for c, s in zip(c15, trend_series(c15))}
        side, sides = 0, []
        for c in candles5:
            key = c.open_time - timedelta(minutes=10)      # bara de 15 minute care se încheie odată cu aceasta
            if key in by_time and c.open_time.minute % 15 == 10:
                side = by_time[key][0]
            sides.append(side)
    else:
        sides = [s for s, _ in revert_series(candles5)]
    gross = net = 0.0
    trades = 0
    per_day: dict = {}
    for i in range(len(candles5) - 1):
        r = candles5[i + 1].close / candles5[i].close - 1
        prev = sides[i - 1] if i else 0
        change = abs(sides[i] - prev)
        cost = change * cost_pct / 100
        trades += change > 0
        g = sides[i] * r
        gross += g
        net += g - cost
        day = candles5[i + 1].open_time.date().isoformat()
        per_day[day] = per_day.get(day, 0.0) + g - cost
    return {"gross": gross, "net": net, "trades": trades, "per_day": per_day,
            "exposure": sum(1 for s in sides if s) / max(1, len(sides))}


def backtest(kind: str, bars: dict, costs: dict) -> dict:
    """Portofoliu cu pondere egală pe toate monedele (expunere ≤ 1x); rezultatul pe zi și total, brut și net."""
    results = {n: backtest_market(kind, c, costs[n]) for n, c in bars.items() if len(c) > 300}
    if not results:
        return {"nota": "fără date"}
    k = len(results)
    days = sorted({d for r in results.values() for d in r["per_day"]})
    daily = [sum(r["per_day"].get(d, 0.0) for r in results.values()) / k for d in days]
    equity, peak, dd = 1.0, 1.0, 0.0
    for r in daily:
        equity *= 1 + r
        peak = max(peak, equity)
        dd = max(dd, 1 - equity / peak)
    sd = pstdev(daily) if len(daily) > 1 else 0.0
    return {"strategie": kind, "monede": k, "zile": len(days),
            "brut_pct": round(100 * sum(r["gross"] for r in results.values()) / k, 2),
            "net_pct": round(100 * (equity - 1), 2),
            "medie_zi_pct": round(100 * mean(daily), 3) if daily else None,
            "sharpe_anual": round(mean(daily) / sd * sqrt(365), 2) if sd > 0 else None,
            "scadere_maxima_pct": round(100 * dd, 2),
            "tranzactii": sum(r["trades"] for r in results.values()),
            "zile_pe_plus_pct": round(100 * sum(1 for r in daily if r > 0) / len(daily), 1) if daily else None,
            "expunere_medie_pct": round(100 * mean(r["exposure"] for r in results.values()), 1),
            "cele_mai_bune": sorted(((round(100 * r["net"], 2), n) for n, r in results.items()), reverse=True)[:5],
            "cele_mai_slabe": sorted((round(100 * r["net"], 2), n) for n, r in results.items())[:5]}


def _series_by_close(kind: str, candles5) -> list[tuple[datetime, tuple]]:
    """(momentul încheierii, semnal) pentru fiecare lumânare a regulii: 15 minute la trend, 5 minute la revenire."""
    if kind == TREND:
        c15 = resample(candles5, 15)
        return [(c.open_time + timedelta(minutes=15), s) for c, s in zip(c15, trend_series(c15))]
    return [(c.open_time + STEP, s) for c, s in zip(candles5, revert_series(candles5))]


def backtest_engine(kind: str, bars: dict, start: datetime, end: datetime, path: Path) -> dict:
    """Test pe istoric cu ACELAȘI motor ca P27/P28 (v2, după auditul din 5.11): la fiecare 10 minute se dau motorului
    lumânările de 5 minute încheiate, apoi strategy_decide (aceeași funcție ca în cont) alege cele mai puternice 10
    semnale, câte 10%, cu stopul contului, costurile instrumentelor, limitele motorului și execuția la deschiderea
    lumânării următoare. Singura diferență față de cont: semnalul se calculează o dată pe tot istoricul, nu pe
    fereastra de 3 zile a contului (EMA pornește de mai devreme și starea revenirii nu se resetează la marginea
    ferestrei); efectul e neglijabil după primele ore, verificat în teste pe aceleași lumânări."""
    from bisect import bisect_right
    chosen = [m for m in markets(crypto_only=True) if len(bars.get(m.name) or []) > 300]
    if not chosen:
        return {"nota": "fără date"}
    path = Path(path)
    if path.exists():
        path.unlink()
    engine = open_account(path, None, start)
    # Baza de test e de unică folosință: fără fsync la fiecare bară (de ~8 ori mai repede); logica e neatinsă.
    engine._db.execute("PRAGMA synchronous = OFF")
    try:
        for m in chosen:
            engine.register_instrument(paper_runner.instrument_for(m))
        series = {m.name: _series_by_close(kind, bars[m.name]) for m in chosen}
        closes = {n: [t for t, _ in v] for n, v in series.items()}
        done = {m.name: 0 for m in chosen}
        t = start.replace(second=0, microsecond=0) - timedelta(minutes=start.minute % 10)
        curve, cycles = [], 0
        while t <= end:
            pending = []
            for m in chosen:
                candles, i = bars[m.name], done[m.name]
                while i < len(candles) and candles[i].open_time + STEP <= t:
                    pending.append((candles[i].open_time, m.name, candles[i]))
                    i += 1
                done[m.name] = i
            pending.sort(key=lambda x: (x[0], x[1]))
            for _, name, candle in pending:
                engine.on_bar(name, candle)
            signals, data = {}, {}
            for n in closes:
                k = bisect_right(closes[n], t) - 1
                signals[n] = series[n][k][1] if k >= 0 else (0, 0.0)
                i = done[n]
                if i > paper_runner.RunnerConfig().atr_period:
                    data[n] = bars[n][i - 15:i]
            strategy_decide(engine, kind, signals, data, t, len(pending))
            curve.append((t, engine.equity()))
            cycles += 1
            t += timedelta(minutes=10)
        fills = engine.fills()
    finally:
        engine.close()
    by_day = {}
    for when, eq in curve:
        by_day[when.date().isoformat()] = eq
    days = sorted(by_day)
    values = [CAPITAL] + [by_day[d] for d in days]
    daily = [b / a - 1 for a, b in zip(values, values[1:]) if a > 0]
    peak, dd = CAPITAL, 0.0
    for _, eq in curve:
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
    sd = pstdev(daily) if len(daily) > 1 else 0.0
    cost = sum(abs(f["quantity"]) * f["price"] for f in fills)
    return {"strategie": kind, "varianta": "motor (v2): aceeași execuție ca în cont", "monede": len(chosen),
            "zile": len(days), "cicluri": cycles, "net_pct": round(100 * (curve[-1][1] / CAPITAL - 1), 2),
            "medie_zi_pct": round(100 * mean(daily), 3) if daily else None,
            "sharpe_anual": round(mean(daily) / sd * sqrt(365), 2) if sd > 0 else None,
            "scadere_maxima_pct": round(100 * dd, 2), "tranzactii": len(fills),
            "iesiri": {r: sum(f["reason"] == r for f in fills) for r in ("stop_loss", "take_profit", "order")},
            "rulaj_x_capital": round(cost / CAPITAL, 1),
            "zile_pe_plus_pct": round(100 * sum(1 for r in daily if r > 0) / len(daily), 1) if daily else None}


def run_backtest(days: int, out: Path, fetch=fetch_bars, now: datetime | None = None, engine: bool = True) -> dict:
    now = now or datetime.now(timezone.utc)
    end = now.replace(second=0, microsecond=0) - timedelta(minutes=now.minute % 5)
    start = end - timedelta(days=days)
    bars, errors, costs = {}, {}, {}
    for m in markets(crypto_only=True):
        try:
            bars[m.name] = fetch(m, start, end)
            costs[m.name] = m.fee_pct + m.slippage_pct
        except MarketDataError as exc:
            errors[m.name] = str(exc)[:120]
    result = {"time": now.isoformat(timespec="minutes"), "start": start.isoformat(), "end": end.isoformat(),
              "E-017": backtest(TREND, bars, costs), "E-018": backtest(REVERT, bars, costs), "erori": errors,
              "nota": ("E-017/E-018 = varianta SIMPLIFICATĂ (v1, păstrată pentru comparație): toate monedele egal, fără "
                       "stop, fără selecția celor 10. E-017-motor/E-018-motor = v2, aceeași execuție ca în conturile "
                       "P27/P28. Rezultat pe o singură perioadă: de citit cu prudență.")}
    if engine:
        warm = start + timedelta(days=1)                   # ca în cont: semnalele au nevoie de istoric
        tmp = out.parent if isinstance(out, Path) else Path(out).parent
        result["E-017-motor"] = backtest_engine(TREND, bars, warm, end, Path(tmp) / "bt-p27.sqlite")
        result["E-018-motor"] = backtest_engine(REVERT, bars, warm, end, Path(tmp) / "bt-p28.sqlite")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="intraday_live")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cycle", help="un pas la 10 minute pentru P26–P28")
    c.add_argument("--dir", required=True, help="dosarul de stare (ramura intraday)")
    c.add_argument("--p24", help="paper.sqlite al lui P24 (de pe ramura formatii-ai)")
    c.add_argument("--daily-dir", help="lumânări zilnice (date-piete zilnic + crypto50), pentru reciclare")
    b = sub.add_parser("backtest", help="E-017/E-018 pe ultimele zile de lumânări de 5 minute (crypto)")
    b.add_argument("--days", type=int, default=30)
    b.add_argument("--out", required=True)
    b.add_argument("--simplified-only", action="store_true", help="doar varianta simplificată (v1), fără motor")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    if args.cmd == "cycle":
        status = cycle(Path(args.dir), Path(args.p24) if args.p24 else None,
                       Path(args.daily_dir) if args.daily_dir else None, now)
        print(json.dumps({k: status[k] for k in ("time", "markets_with_bars", "accounts")}, ensure_ascii=False))
        broken = [k for k, v in status["accounts"].items() if "error" in v and k != TWIN]
        return 1 if broken else 0
    result = run_backtest(args.days, Path(args.out), engine=not args.simplified_only)
    print(json.dumps({k: result[k] for k in result if k.startswith("E-")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
