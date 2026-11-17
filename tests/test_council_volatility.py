"""Regresie: volatilitatea anualizată folosea mereu sqrt(365), și pentru piețele cu 5 zile pe săptămână."""
from datetime import datetime, timedelta, timezone
from math import isclose, sqrt

from src.bnd.council_context import _volatility
from src.bnd.market_data import Candle

START = datetime(2026, 1, 5, tzinfo=timezone.utc)          # luni


def series(days):
    prices = [100 * (1.01 if i % 2 else 0.99) ** (i % 2) for i in range(len(days))]
    return [Candle(d, p, p * 1.02, p * 0.98, p, 1) for d, p in zip(days, prices)]


def test_crypto_trading_every_day_is_annualized_with_365():
    every_day = [START + timedelta(days=i) for i in range(61)]
    weekdays = [d for d in (START + timedelta(days=i) for i in range(90)) if d.weekday() < 5][:61]
    crypto, stocks = _volatility(series(every_day), 20), _volatility(series(weekdays), 20)

    # Aceleași randamente zilnice: diferența vine doar din numărul de zile de tranzacționare pe an.
    assert isclose(crypto / stocks, sqrt(365 / (365 * 20 / 28)), rel_tol=1e-9)
    assert stocks < crypto                              # acțiunile nu mai sunt umflate cu sqrt(365/260)
