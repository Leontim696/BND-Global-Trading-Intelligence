"""Decontarea unei decizii în trei feluri, după regulile bune de la cercetarea TradingAgents (Apache-2.0, idei reimplementate):

1. ``raw``: de la prețul deciziei (ultima închidere cunoscută) la prima închidere de la orizont (regula veche, rămâne).
2. ``entry_next``: intrarea la PRIMA ÎNCHIDERE DE DUPĂ data deciziei, nu la cea din ziua deciziei. Un vot dat după
   închidere nu se poate executa la prețul care era deja pe tablă; botul nostru oricum intră la deschiderea următoare.
3. ``alpha``: randamentul peste cel al benchmark-ului (SP500 pentru restul, BITCOIN pentru cripto), pe aceleași
   date. Într-o piață care urcă, o rată de reușită brută e umflată; alpha arată dacă votul a adăugat ceva.

Se folosesc doar închideri finale: o bară din ziua deciziei sau mai nouă decât data țintă nu intră la intrare.
Nimic de aici nu schimbă ``outcome_return``; rezultatul se adaugă în ``meta["settle"]``.
"""

from datetime import datetime, timedelta

from .coins import COINS

CRYPTO = {"BITCOIN", "ETHEREUM", "SOLANA", "BNB", "XRP"} | {name for name, _, _ in COINS}
EQUITY_BENCHMARK = "SP500"
CRYPTO_BENCHMARK = "BITCOIN"


def benchmark_for(symbol: str) -> str | None:
    """Benchmark-ul unei piețe; None pentru benchmark-ul însuși (alpha față de sine nu are sens)."""
    benchmark = CRYPTO_BENCHMARK if symbol in CRYPTO else EQUITY_BENCHMARK
    return None if symbol == benchmark else benchmark


def _closes(candles):
    return [(c.open_time, c.close) for c in candles if c.close and c.close > 0]


def _window(candles, decision_time: datetime, target: datetime):
    """(intrare_next, ieșire, intrare_brută) pentru o serie: închideri finale, fără bara zilei deciziei."""
    series = _closes(candles)
    exit_ = next((c for t, c in series if t >= target), None)
    exit_time = next((t for t, c in series if t >= target), None)
    entry_next = next(((t, c) for t, c in series if t.date() > decision_time.date()), None)
    raw = next(((t, c) for t, c in reversed(series) if t.date() <= decision_time.date()), None)
    return entry_next, (exit_time, exit_), raw


def details(symbol: str, decision_time: datetime, horizon_days: int, candles_by_symbol: dict) -> dict:
    """Randamentele alternative ale unei decizii; câmpurile imposibil de calculat lipsesc."""
    target = decision_time + timedelta(days=horizon_days)
    entry_next, (exit_time, exit_close), raw = _window(candles_by_symbol.get(symbol, ()), decision_time, target)
    out = {}
    if exit_close is None:
        return out
    if entry_next and entry_next[0] < exit_time:
        out["entry_next_return"] = exit_close / entry_next[1] - 1
        out["entry_next_date"] = entry_next[0].date().isoformat()
    benchmark = benchmark_for(symbol)
    if benchmark and benchmark in candles_by_symbol:
        b_entry, (b_exit_time, b_exit), b_raw = _window(candles_by_symbol[benchmark], decision_time, target)
        out["benchmark"] = benchmark
        if raw and b_raw and b_exit:
            out["benchmark_return_raw"] = b_exit / b_raw[1] - 1
            out["alpha_raw"] = exit_close / raw[1] - b_exit / b_raw[1]
        if "entry_next_return" in out and b_entry and b_exit_time and b_entry[0] < b_exit_time:
            out["benchmark_return_next"] = b_exit / b_entry[1] - 1
            out["alpha_next"] = out["entry_next_return"] - out["benchmark_return_next"]
    return out
