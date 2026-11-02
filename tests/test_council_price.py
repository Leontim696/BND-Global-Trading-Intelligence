"""Regresie: memecoin-urile ajungeau la consiliu cu prețul „0.0000”."""
from datetime import datetime, timedelta, timezone

from src.bnd import drive_pack
from src.bnd.council_context import build_context, price_text
from src.bnd.market_data import Candle


def test_small_prices_keep_four_significant_digits_and_large_ones_are_unchanged():
    assert price_text(5e-06) == "0.000005000"
    assert price_text(2.323e-05) == "0.00002323"
    assert price_text(0.947) == "0.9470"
    assert price_text(755.72) == "755.7200" and price_text(0.0) == "0.0000"


def test_memecoin_context_shows_a_real_price():
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    candles = [Candle(start + timedelta(days=i), 5e-06, 6e-06, 4e-06, 5e-06 * (1 + i / 1000), 1) for i in range(80)]
    text = build_context("PEPE", candles)
    assert "preț 0.0000," not in text and "preț 0.00000" in text


def test_drive_pack_still_parses_the_new_price_line():
    line = "Preț 0.000005000 (închidere 2026-10-30); regula simplă a botului: vinde; cost 0.027 $."
    assert drive_pack.PRICE.match(line).group("price") == "0.000005000"
