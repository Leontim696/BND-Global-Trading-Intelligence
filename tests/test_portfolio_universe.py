"""Acțiuni, limita de concentrare și harta instrumentelor."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.bnd.instruments import INSTRUMENTS, instrument, table
from src.bnd.portfolio import PortfolioConfig, _Book, target_weights
from src.bnd.universe import STOCK_UNIVERSE, UNIVERSES, Market, esma_margin_pct, select

ROOT = Path(__file__).resolve().parents[1]


def test_stock_universe_is_selectable_with_sectors_and_costs():
    stocks = select(universe="stocks")

    assert len(stocks) == 16 and {m.asset_class for m in stocks} == {"stock"}
    assert {m.sector for m in stocks} == {"tehnologie", "consum", "sănătate", "energie",
                                           "financiar", "industrie"}
    assert select(["AAPL"], universe="stocks")[0].fee_pct == 0.02
    assert select(classes=["stock"], universe="stocks") == STOCK_UNIVERSE
    assert esma_margin_pct(stocks[0]) == 20.0                     # acțiuni: 5:1


DATES = [datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(30)]


def books(markets, signals):
    out = []
    for k, (market, signal) in enumerate(zip(markets, signals)):
        book = _Book(market, [], lambda history: 0)
        book.signal, book.vol = signal, 0.2
        book.returns = {d: 0.01 * (-1) ** i for i, d in enumerate(DATES)}
        out.append(book)
    return out


def test_group_limit_scales_down_a_crowded_sector_only():
    tech = [Market(n, n, "stock", 0.02, 0.03, sector="tehnologie") for n in ("A", "B", "C")]
    energy = Market("D", "D", "stock", 0.02, 0.03, sector="energie")
    markets = tech + [energy]
    free = PortfolioConfig(vol_lookback=20, max_leverage=20, max_weight=2, target_vol_pct=40)
    capped = PortfolioConfig(vol_lookback=20, max_leverage=20, max_weight=2, target_vol_pct=40,
                             max_group_weight=0.5)

    before = target_weights(books(markets, [1, 1, 1, 1]), free, DATES)
    after = target_weights(books(markets, [1, 1, 1, 1]), capped, DATES)

    assert sum(abs(before[n]) for n in "ABC") > 0.5
    assert sum(abs(after[n]) for n in "ABC") == pytest.approx(0.5)
    assert after["D"] == pytest.approx(min(before["D"], 0.5))     # sectorul lui nu e aglomerat


def test_group_limit_validation_and_class_fallback():
    for bad in (0, -1, 25, float("nan")):
        with pytest.raises(ValueError):
            PortfolioConfig(max_group_weight=bad)
    fx = [Market(n, n, "forex", 0.002, 0.005) for n in ("E", "F")]
    config = PortfolioConfig(vol_lookback=20, max_leverage=20, max_weight=2, target_vol_pct=40,
                             max_group_weight=0.3)

    weights = target_weights(books(fx, [1, 1]), config, DATES)

    assert sum(weights.values()) == pytest.approx(0.3)            # fără sector: grupul e clasa


def test_every_market_has_an_instrument_and_the_doc_is_current():
    names = {m.name for universe in UNIVERSES.values() for m in universe}

    for name in names:
        asset, future, cfd = instrument(name)
        assert asset and future and cfd, name
    assert set(INSTRUMENTS) <= names
    with pytest.raises(KeyError):
        instrument("NU_EXISTA")
    assert (ROOT / "docs" / "INSTRUMENTE.md").read_text(encoding="utf-8") == table()


def test_group_limit_with_no_history_returns_zero_weights_instead_of_crashing():
    markets = [Market(n, n, "forex", 0.002, 0.005) for n in ("E", "F")]
    config = PortfolioConfig(vol_lookback=20, max_group_weight=0.3)

    assert target_weights(books(markets, [1, 1]), config, []) == {"E": 0.0, "F": 0.0}
