"""Top 50 cripto: arhivă best-effort și rezumat, fără rețea."""

from datetime import datetime, timedelta, timezone

from src.bnd import crypto50, dashboard
from src.bnd.market_data import Candle, MarketDataError

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def fake_fetch(symbol, interval, start, end, timeout=30.0):
    if symbol == "WIFUSDT":
        raise MarketDataError("Binance request failed")
    days = (end - start).days
    base = 100.0 if symbol != "PEPEUSDT" else 0.00001
    return [Candle(start + timedelta(days=i), base * (1 + 0.001 * i), base * (1.01 + 0.001 * i),
                   base * (0.99 + 0.001 * i), base * (1 + 0.001 * (i + 1)), 1) for i in range(days)]


def test_list_is_fifty_unique_coins_with_memecoins_and_no_stablecoins():
    names = [c[0] for c in crypto50.COINS]
    assert len(names) == 50 == len(set(names))
    assert {"DOGE", "SHIB", "PEPE", "BONK", "WIF"} <= {c[0] for c in crypto50.COINS if c[2]}
    assert not {"USDT", "USDC", "DAI"} & set(names)


def test_update_is_incremental_and_one_failing_coin_does_not_stop_the_rest(tmp_path):
    first = crypto50.update(tmp_path, fake_fetch, NOW, years=1)
    second = crypto50.update(tmp_path, fake_fetch, NOW + timedelta(days=2), years=1)

    assert not first["coins"]["WIF"]["ok"] and first["coins"]["BTC"]["ok"]
    assert sum(v["ok"] for v in first["coins"].values()) == 49
    assert second["coins"]["BTC"]["added"] == 2                     # doar zilele noi
    assert not (tmp_path / "WIF.csv").exists() and (tmp_path / "status.json").exists()


def test_summary_has_price_changes_signal_and_meme_flag(tmp_path):
    crypto50.update(tmp_path, fake_fetch, NOW, years=1)

    rows = {r["name"]: r for r in crypto50.summary(tmp_path)}

    assert len(rows) == 49 and rows["PEPE"]["meme"] and not rows["BTC"]["meme"]
    assert rows["BTC"]["d7"] > 0 and rows["BTC"]["signal"] == 1     # trend în creștere
    assert rows["PEPE"]["price"] < 0.001


def test_dashboard_carries_the_top50_table(tmp_path):
    crypto50.update(tmp_path / "t", fake_fetch, NOW, years=1)
    data = dashboard.collect(None, None, None, None, NOW, top50=tmp_path / "t")
    assert len(data["top50"]) == 49
    assert dashboard.collect(None, None, None, None, NOW)["top50"] == []
