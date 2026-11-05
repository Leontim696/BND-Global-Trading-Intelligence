"""Divizări (split) și comasări la acțiuni/ETF, adăugat pe 5.11.2026 după ITA (~3:1).

Sursa de prețuri ajustează istoricul după un split, dar motorul ține cantitatea și prețurile vechi; fără ajustare, o
poziție short ar apărea cu un câștig fals de ~67% (și una long cu o pierdere falsă). Detectarea are nevoie de
confirmarea din istoric: închiderea zilei deja procesate de motor apare în datele noi de exact 2, 3, 4… ori mai mică
(sau mai mare). O cotație greșită doar în ziua nouă nu e luată drept split.
"""

from datetime import datetime
from math import isfinite

from .paper_engine import PaperEngine, PaperEngineError, _iso

RATIOS = (2, 3, 4, 5, 8, 10, 15, 20, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 10)
TOLERANCE = 0.03


def detect(engine: PaperEngine, data: dict) -> dict:
    """{piață: {factor, mark_vechi, inchidere_ajustata, zi}} pentru divizările confirmate de istoricul descărcat."""
    out = {}
    for name, candles in data.items():
        mark = engine.mark(name)
        if not mark:
            continue
        seen = datetime.fromisoformat(mark["time"])
        same = next((c for c in reversed(candles) if c.open_time == seen), None)
        if same is None or not same.close > 0:
            continue
        ratio = mark["price"] / same.close
        for k in RATIOS:
            if abs(ratio / k - 1) <= TOLERANCE:
                out[name] = {"factor": k, "mark_vechi": mark["price"], "inchidere_ajustata": same.close,
                             "zi": seen.date().isoformat()}
                break
    return out


def apply(engine: PaperEngine, symbol: str, factor: float, now: datetime, evidence: dict | None = None) -> dict:
    """`factor` unități noi pentru una veche (3 = split 3:1). Valoarea poziției rămâne aceeași: cantitatea × factor,
    iar prețurile poziției, ale marcajului, ale istoricului de închideri și ale ordinelor în așteptare ÷ factor.
    Banii din cont nu se schimbă. Totul într-o singură tranzacție, notat în jurnal ca „split”."""
    if not (isfinite(factor) and factor > 0) or factor == 1:
        raise PaperEngineError("Factor de split invalid")
    db = engine._db
    with engine._transaction():
        db.execute("UPDATE positions SET quantity = quantity * ?, avg_price = avg_price / ?, stop_loss = stop_loss / ?,"
                   " take_profit = take_profit / ?, best_price = best_price / ? WHERE symbol = ?",
                   (factor, factor, factor, factor, factor, symbol))
        db.execute("UPDATE marks SET price = price / ?, previous_close = previous_close / ? WHERE symbol = ?",
                   (factor, factor, symbol))
        db.execute("UPDATE closes SET price = price / ? WHERE symbol = ?", (factor, symbol))
        # Ordinele în așteptare: doar partea neumplută se înmulțește (ce s-a umplut rămâne legat de tranzacțiile vechi).
        db.execute("UPDATE orders SET quantity = filled_quantity + (quantity - filled_quantity) * ?,"
                   " limit_price = limit_price / ?, stop_loss = stop_loss / ?, take_profit = take_profit / ?"
                   " WHERE symbol = ? AND status IN ('PENDING', 'PARTIAL')",
                   (factor, factor, factor, factor, symbol))
        last_fill = db.execute("SELECT COALESCE(MAX(id), 0) FROM fills").fetchone()[0]
        payload = {"symbol": symbol, "factor": factor, "dupa_tranzactia": last_fill, **(evidence or {})}
        engine._log("split", payload, _iso(now))
    return payload
