"""Adaptive Position Recycling: ce se face cu capitalul eliberat când o poziție se închide pe take profit sau pe stop.

Cerut de proprietar pe 4.11.2026, ca test paralel cu contul oficial (bani virtuali, fără apeluri AI). Două moduri,
cu ACELEAȘI limite de risc, ca să se vadă dacă reciclarea aduce un avantaj real sau doar mai multe tranzacții:

    obisnuit   după un take profit/stop, piața stă în pauză (aceeași direcție) câteva zile; capitalul eliberat
               rămâne lichid până la următoarea țintă a strategiei.
    reciclare  aceeași pauză, dar capitalul eliberat se mută imediat (la rularea zilnică) pe următoarele cele mai
               bune semnale care nu sunt deja ținute, cu reguli de protecție:
               - expunerea totală nu trece de plafonul contului (2x) și o piață nu trece de plafonul ei (25%);
               - protecție la corelație: un „grup” de piețe care se mișcă împreună (corelație > 0,7 pe 60 de zile,
                 aceeași direcție) nu poate depăși 50% din cont, ca 80 de poziții să nu fie de fapt un singur pariu;
               - pierdere zilnică: dacă de la rularea trecută contul a pierdut ≥ 2%, nu se deschide nimic nou azi;
               - blocare la performanță slabă: dacă pe ultimele 10 rulări contul a pierdut ≥ 3% sau e cu ≥ 8% sub
                 vârf, reciclarea se oprește (contul se poartă ca „obișnuit”) până își revine;
               - cel mult 10 poziții noi reciclate pe zi.

Sistemul decide o dată pe zi (ca restul conturilor), deci „imediat” înseamnă la următoarea rulare zilnică.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import log, sqrt
from statistics import mean, pstdev

EXIT_REASONS = ("take_profit", "stop_loss", "trailing_stop")


@dataclass(frozen=True)
class RecycleRules:
    mode: str                         # "obisnuit" sau "reciclare"
    cooldown_days: int = 5
    max_cluster: float = 0.5          # |pondere| totală într-un grup corelat, aceeași direcție
    corr_threshold: float = 0.7
    corr_lookback: int = 60
    daily_loss_pct: float = 2.0
    perf_window: int = 10
    perf_floor_pct: float = -3.0
    max_drawdown_pct: float = 8.0
    max_new_per_day: int = 10

    def __post_init__(self):
        if self.mode not in ("obisnuit", "reciclare"):
            raise ValueError("recycle mode must be 'obisnuit' or 'reciclare'")


def _returns(candles, n):
    closes = [c.close for c in candles[-(n + 1):]]
    return [log(b / a) for a, b in zip(closes, closes[1:]) if a > 0 and b > 0]


def _corr(a, b):
    k = min(len(a), len(b))
    if k < 20:
        return 0.0
    a, b = a[-k:], b[-k:]
    sa, sb = pstdev(a), pstdev(b)
    if sa == 0 or sb == 0:
        return 0.0
    ma, mb = mean(a), mean(b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (k * sa * sb)


def recent_exits(fills, now: datetime, days: int) -> dict:
    """{piață: direcția poziției închise (+1 long, -1 short)} pentru ieșirile pe TP/stop din ultimele `days` zile."""
    since = now - timedelta(days=days)
    out = {}
    for f in fills:
        if f["reason"] not in EXIT_REASONS:
            continue
        if datetime.fromisoformat(f["time"]) < since:
            continue
        out[f["symbol"]] = -1 if f["quantity"] > 0 else 1    # o vânzare închide un long, o cumpărare un short
    return out


def guard(history: list[float], peak: float, rules: RecycleRules) -> str | None:
    """Motivul pentru care reciclarea e blocată azi, sau None. `history` = valorile contului la rulările trecute."""
    if len(history) >= 2 and history[-2] > 0 and 100 * (history[-1] / history[-2] - 1) <= -rules.daily_loss_pct:
        return f"pierdere zilnică ≥ {rules.daily_loss_pct:g}%"
    window = history[-(rules.perf_window + 1):]
    if len(window) >= 2 and window[0] > 0 and 100 * (window[-1] / window[0] - 1) <= rules.perf_floor_pct:
        return f"pierdere ≥ {-rules.perf_floor_pct:g}% pe ultimele {rules.perf_window} rulări"
    if history and peak > 0 and 100 * (1 - history[-1] / peak) >= rules.max_drawdown_pct:
        return f"≥ {rules.max_drawdown_pct:g}% sub vârf"
    return None


def adjust(weights: dict, signals: dict, data: dict, exits: dict, rules: RecycleRules,
           max_weight: float, max_gross: float, blocked: str | None = None) -> tuple[dict, dict]:
    """Ponderile de azi după regulile de reciclare și raportul a ce s-a făcut."""
    w = dict(weights)
    cooled = [m for m, side in exits.items()
              if m in w and w[m] and (1 if w[m] > 0 else -1) == side]
    freed = sum(abs(w[m]) for m in cooled)
    for m in cooled:
        w[m] = 0.0
    info = {"mode": rules.mode, "cooled": sorted(cooled), "freed": round(freed, 4), "reassigned": 0.0,
            "added": {}, "blocked": None, "skipped_correlation": []}
    if rules.mode == "obisnuit" or freed <= 0:
        return w, info
    if blocked:
        info["blocked"] = blocked
        return w, info
    rets = {m: _returns(c, rules.corr_lookback) for m, c in data.items()}
    vol = {m: (pstdev(r) * sqrt(252) if len(r) > 10 else 0.0) for m, r in rets.items()}
    candidates = sorted(
        (m for m, s in signals.items()
         if s and m not in cooled and m not in exits and m in rets and vol.get(m, 0) > 0
         and abs(w.get(m, 0.0)) < max_weight - 1e-9
         and (not w.get(m) or (w[m] > 0) == (s > 0))),
        key=lambda m: -abs(signals[m]) / vol[m])
    remaining, gross, new = freed, sum(abs(v) for v in w.values()), 0
    for m in candidates:
        if remaining <= 1e-9 or new >= rules.max_new_per_day:
            break
        side = 1 if signals[m] > 0 else -1
        room = min(remaining, max_weight - abs(w.get(m, 0.0)), max_gross - gross)
        if room <= 1e-9:
            break
        cluster = sum(abs(v) for k, v in w.items()
                      if k != m and v and (1 if v > 0 else -1) == side
                      and _corr(rets[m], rets.get(k, [])) > rules.corr_threshold)
        room = min(room, rules.max_cluster - cluster - abs(w.get(m, 0.0)))
        if room <= 1e-9:
            info["skipped_correlation"].append(m)
            continue
        w[m] = w.get(m, 0.0) + side * room
        info["added"][m] = round(side * room, 4)
        remaining -= room
        gross += room
        new += 1
    info["reassigned"] = round(freed - remaining, 4)
    return w, info
