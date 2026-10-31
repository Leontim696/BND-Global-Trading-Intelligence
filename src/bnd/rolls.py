"""Ajustarea sărturilor de rolare la futures (serii continue neajustate).

Seriile continue de futures (`=F` la Yahoo) sar când contractul expiră și se trece
la următorul: un salt pe care nimeni nu l-ar fi putut câștiga. ``detect_jumps``
arată zilele suspecte (deschiderea diferă mult de închiderea de ieri); dacă se
știu datele reale de rolare, ``back_adjust`` mută tot istoricul dinainte cu
raportul sărit, ca saltul să dispară. Universul ETF evită problema din construcție.
"""

from datetime import date
from typing import Sequence

from .market_data import Candle


def detect_jumps(candles: Sequence[Candle], threshold: float = 0.03) -> list[tuple[date, float]]:
    """(zi, raport deschidere/închiderea anterioară) pentru salturi peste prag."""
    if not 0 < threshold < 1:
        raise ValueError("threshold între 0 și 1")
    jumps = []
    for previous, current in zip(candles, candles[1:]):
        ratio = current.open / previous.close
        if abs(ratio - 1) > threshold:
            jumps.append((current.open_time.date(), ratio))
    return jumps


def back_adjust(candles: Sequence[Candle], roll_dates: Sequence[date]) -> list[Candle]:
    """Ajustează istoricul dinaintea fiecărei rolări cu saltul din acea zi."""
    wanted = set(roll_dates)
    out = []
    factors = [1.0] * len(candles)
    running = 1.0
    for i in range(len(candles) - 1, 0, -1):
        if candles[i].open_time.date() in wanted:
            running *= candles[i].open / candles[i - 1].close
        factors[i - 1] = running
    for candle, f in zip(candles, factors):
        out.append(Candle(candle.open_time, candle.open * f, candle.high * f, candle.low * f,
                          candle.close * f, candle.volume))
    return out
