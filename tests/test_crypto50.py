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


def test_extra_coins_are_the_forty_five_not_already_covered_and_the_split_is_safe():
    assert len(crypto50.EXTRA) == 45 and not set(crypto50.EXTRA) & set(crypto50.COVERED)
    groups = crypto50.split_markets(["SP500", "SOLANA", "DOGE", "PEPE", "BITCOIN", "XRP"])
    assert groups == {"etf": ["SP500", "BITCOIN"], "yahoo_crypto": ["SOLANA", "XRP"],
                      "binance": ["DOGE", "PEPE"], "defense": [], "stocks": []}
    mixed = crypto50.split_markets(["AAPL", "RHEINMETALL", "LOCKHEED", "GOLD"])
    assert mixed["stocks"] == ["AAPL"] and mixed["defense"] == ["RHEINMETALL", "LOCKHEED"] and mixed["etf"] == ["GOLD"]
    import pytest
    for bad in ("SP500;rm", "a b", "$(x)", "bnb"):
        with pytest.raises(ValueError):
            crypto50.split_markets([bad])
    assert crypto50.main(["--split", "SP500;rm -rf /"]) == 2


def test_update_only_fetches_the_requested_coins(tmp_path):
    status = crypto50.update(tmp_path, fake_fetch, NOW, years=1, only={"DOGE"})
    assert list(status["coins"]) == ["DOGE"] and (tmp_path / "DOGE.csv").exists()
    assert not (tmp_path / "BTC.csv").exists()


def test_unified_universe_has_us_stocks_and_defense_with_their_own_sector():
    from src.bnd.universe import DEFENSE_CURRENCY, DEFENSE_NAMES, UNIVERSES
    unic = {m.name: m for m in UNIVERSES["unic"]}
    assert len(unic) == 101 and {"AAPL", "NVDA", "RHEINMETALL", "LOCKHEED", "ITA"} <= set(unic)
    assert all(unic[n].sector == "armament" and unic[n].asset_class == "stock" for n in DEFENSE_NAMES)
    assert unic["AAPL"].sector == "tehnologie"
    assert DEFENSE_CURRENCY["RHEINMETALL"] == "EUR" and DEFENSE_CURRENCY["LOCKHEED"] == "USD"
    from src.bnd.council_context import label
    assert "apărare" in label("RHEINMETALL") and "EUR" in label("RHEINMETALL")
    from src.bnd.council_daily import ASSET_CLASS
    assert ASSET_CLASS["SAAB"] == "armament"


def test_every_universe_used_by_the_workflows_is_accepted_by_the_fetch_and_runner_clis():
    import re
    from pathlib import Path
    from src.bnd import backtest_cli, paper_runner
    from src.bnd.universe import UNIVERSES
    used = set()
    for path in Path(".github/workflows").glob("*.yml"):
        used |= set(re.findall(r"--universe\s+([a-z]+)", path.read_text(encoding="utf-8")))
    assert used <= set(UNIVERSES), used - set(UNIVERSES)
    for universe in sorted(used):
        parser = backtest_cli.build_parser()
        assert parser.parse_args(["fetch-universe", "--universe", universe, "--out-dir", "x"]).universe == universe
        assert paper_runner.build_parser().parse_args(
            ["--state", "s", "--data-dir", "d", "--universe", universe]).universe == universe
