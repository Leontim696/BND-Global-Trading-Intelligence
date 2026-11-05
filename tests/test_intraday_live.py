"""Execuția intraday la 10 minute (5.11): geamănul lui P24 (P26), trend (P27), revenire (P28) și testul pe istoric."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from src.bnd import intraday_live as il
from src.bnd.market_data import Candle, MarketDataError
from src.bnd.paper_engine import PaperEngine
from tests.test_idei_4_11 import _run

T0 = datetime(2026, 11, 5, 0, 0, tzinfo=timezone.utc)


def _bars(n, start=T0, price=100.0, step=lambda i: 0.001):
    out = []
    for i in range(n):
        o = price
        price *= 1 + step(i)
        out.append(Candle(start + i * il.STEP, o, max(o, price) * 1.001, min(o, price) * 0.999, price, 1e6))
    return out


def test_perechea_binance():
    by = {m.name: m for m in il.markets()}
    assert il.binance_pair(by["BITCOIN"]) == "BTCUSDT" and il.binance_pair(by["DOGE"]) == "DOGEUSDT"
    assert il.binance_pair(by["GOLD"]) is None
    assert {m.asset_class for m in il.markets(crypto_only=True)} <= set(il.CRYPTO)


def test_yahoo_intraday_si_resample():
    stamps = [int((T0 + i * il.STEP).timestamp()) for i in range(6)]
    payload = {"chart": {"result": [{"timestamp": stamps, "indicators": {"quote": [{
        "open": [1, 2, 3, None, 5, 6], "high": [1, 2, 3, 4, 5, 6], "low": [1, 2, 3, 4, 5, 6],
        "close": [1, 2, 3, 4, 5, 6], "volume": [1] * 6}]}}]}}
    bars = il.parse_yahoo_intraday(payload)
    assert len(bars) == 5 and bars[0].open_time == T0
    full = _bars(7)
    r = il.resample(full, 15)
    assert len(r) == 2 and r[0].open == full[0].open and r[0].close == full[2].close   # al treilea grup e incomplet


def test_trend_si_revenire():
    up = _bars(15 * 3 * 100, step=lambda i: 0.0004 + (0.002 if i % 2 else -0.0018))
    assert il.strategy_signal(il.TREND, up)[0] == 1
    flat = _bars(60, step=lambda i: 0.0005 if i % 2 else -0.0005)
    spike = flat + _bars(1, start=flat[-1].open_time + il.STEP, price=flat[-1].close * 1.05, step=lambda i: 0.0)
    side, power = il.strategy_signal(il.REVERT, spike)
    assert side == -1 and power >= il.MR_ENTER
    series = il.revert_series(spike + _bars(30, start=spike[-1].open_time + il.STEP, price=flat[-1].close,
                                            step=lambda i: 0.0005 if i % 2 else -0.0005))
    assert series[-1][0] == 0                                   # a revenit la medie: poziția se închide


def test_alegerea_pozitiilor():
    sig = {f"C{i}": (1 if i % 2 else -1, float(i)) for i in range(15)}
    sig["Z"] = (0, 0.0)
    w = il.pick(sig)
    assert sum(1 for v in w.values() if v) == il.MAX_POSITIONS and w["Z"] == 0.0
    assert w["C14"] == -il.POSITION_WEIGHT and w["C13"] == il.POSITION_WEIGHT and w["C0"] == 0.0


def _fake_fetch(series):
    def fetch(market, start, end):
        if market.name not in series:
            raise MarketDataError("fără date")
        return [c for c in series[market.name] if start <= c.open_time and c.open_time + il.STEP <= end]
    return fetch


def test_ciclu_complet(tmp_path, monkeypatch):
    monkeypatch.setenv("BND_TRADING_MODE", "PAPER")
    report = _run(tmp_path, il.TWIN_OF)                       # P24 cu o singură piață (GOLD), din voturi + regulă
    assert report["weights_base"]["GOLD"] > 0
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = now - timedelta(hours=20)
    gold = _bars(240, start=start, price=report["orders"][0]["price"], step=lambda i: 0.0002)
    btc = _bars(240, start=start, step=lambda i: 0.0008 + (0.002 if i % 2 else -0.0019))
    fetch = _fake_fetch({"GOLD": gold, "BITCOIN": btc})
    st = tmp_path / "st"
    status = il.cycle(st, tmp_path / il.TWIN_OF / "paper.sqlite", tmp_path / "data", now - timedelta(minutes=10),
                      fetch)
    assert status["markets_with_bars"] == 2 and "SP500" in status["fetch_errors"]
    assert all("error" not in v for v in status["accounts"].values()), status["accounts"]
    twin = json.loads((st / il.TWIN / "last_run.json").read_text())
    assert [o["market"] for o in twin["orders"]] == ["GOLD"] and twin["orders"][0]["status"] == "PENDING"
    assert twin["orders"][0]["take_profit"] == pytest.approx(twin["orders"][0]["price"] * 1.07)
    # Al doilea ciclu, 10 minute mai târziu: ordinul se execută la deschiderea lumânării următoare de 5 minute.
    il.cycle(st, tmp_path / il.TWIN_OF / "paper.sqlite", tmp_path / "data", now, fetch)
    engine = PaperEngine.open(st / il.TWIN / "paper.sqlite")
    try:
        assert [p["symbol"] for p in engine.positions()] == ["GOLD"]
        assert len(engine.journal("intraday_run")) == 2
        assert engine.limits().max_portfolio_vol_pct == 0.0
    finally:
        engine.close()
    assert (st / "bars" / "GOLD.csv").exists() and (st / "status.json").exists()


def test_fara_p24_conturile_de_strategie_merg(tmp_path, monkeypatch):
    monkeypatch.setenv("BND_TRADING_MODE", "PAPER")
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    btc = _bars(300, start=now - timedelta(hours=26), step=lambda i: 0.0008 + (0.002 if i % 2 else -0.0019))
    status = il.cycle(tmp_path / "st", None, None, now, _fake_fetch({"BITCOIN": btc}))
    assert "error" in status["accounts"][il.TWIN]
    assert "error" not in status["accounts"][il.TREND] and "error" not in status["accounts"][il.REVERT]


def test_live_refuzat(tmp_path, monkeypatch):
    monkeypatch.setenv("BND_TRADING_MODE", "LIVE")
    with pytest.raises(Exception):
        il.cycle(tmp_path, None, None, T0, _fake_fetch({}))


def test_backtest_costuri():
    bars = {"BITCOIN": _bars(3000, step=lambda i: 0.0003 + (0.002 if i % 2 else -0.0019))}
    free = il.backtest(il.TREND, bars, {"BITCOIN": 0.0})
    paid = il.backtest(il.TREND, bars, {"BITCOIN": 0.5})
    assert free["tranzactii"] == paid["tranzactii"] > 0
    assert paid["net_pct"] < free["net_pct"] and free["brut_pct"] == paid["brut_pct"]
    assert il.backtest(il.REVERT, {"X": _bars(10)}, {"X": 0.1}) == {"nota": "fără date"}


def test_run_backtest_scrie_fisierul(tmp_path):
    now = datetime(2026, 11, 5, 12, 3, tzinfo=timezone.utc)
    series = {"BITCOIN": _bars(1000, start=now - timedelta(days=4), step=lambda i: 0.001 if i % 3 else -0.002)}
    out = tmp_path / "bt.json"
    result = il.run_backtest(3, out, _fake_fetch(series), now)
    assert json.loads(out.read_text())["E-017"]["monede"] == 1 and "BITCOIN" not in result["erori"]


def test_piata_inchisa_nu_primeste_ordine(tmp_path, monkeypatch):
    monkeypatch.setenv("BND_TRADING_MODE", "PAPER")
    report = _run(tmp_path, il.TWIN_OF)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    gold = _bars(60, start=now - timedelta(hours=8), price=report["orders"][0]["price"])   # bursa s-a închis acum 3h
    status = il.cycle(tmp_path / "st", tmp_path / il.TWIN_OF / "paper.sqlite", tmp_path / "data", now,
                      _fake_fetch({"GOLD": gold}))
    assert status["accounts"][il.TWIN]["orders"] == 0
    twin = json.loads((tmp_path / "st" / il.TWIN / "last_run.json").read_text())
    assert twin["markets_open"] == 0 and twin["weights"]["GOLD"] > 0


def test_aplicatia_arata_intraday(tmp_path, monkeypatch):
    from src.bnd import dashboard
    monkeypatch.setenv("BND_TRADING_MODE", "PAPER")
    _run(tmp_path, il.TWIN_OF)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    btc = _bars(300, start=now - timedelta(hours=26), step=lambda i: 0.0008 + (0.002 if i % 2 else -0.0019))
    fetch = _fake_fetch({"BITCOIN": btc})
    st = tmp_path / "st"
    il.cycle(st, tmp_path / il.TWIN_OF / "paper.sqlite", tmp_path / "data", now - timedelta(minutes=10), fetch)
    il.cycle(st, tmp_path / il.TWIN_OF / "paper.sqlite", tmp_path / "data", now, fetch)
    d = dashboard.read_intraday(st)
    assert d["exists"] and [a["key"] for a in d["accounts"]] == list(il.ACCOUNTS)
    assert all(a["exists"] for a in d["accounts"])
    assert dashboard.read_intraday(tmp_path / "lipsa") == {"exists": False}
    out = tmp_path / "app.html"
    assert dashboard.main(["--intraday", str(st), "--template", "src/bnd/dashboard_template.html", "--out", str(out)]) == 0
    html = out.read_text()
    assert "Intraday la 10 minute" in html and il.TREND in html


@pytest.mark.parametrize("kind", [il.TREND, il.REVERT])
def test_backtestul_cu_motor_ia_aceleasi_decizii_ca_contul(tmp_path, kind):
    """Punctul 2 din auditul din 5.11: pe aceleași lumânări, testul pe istoric și contul la 10 minute fac aceleași
    tranzacții (fereastra contului acoperă aici tot istoricul, deci nu există nici diferența de pornire a EMA)."""
    import random
    rng = random.Random(7)
    start = T0 - timedelta(days=2)
    series = {}
    for name in ("BITCOIN", "ETHEREUM", "DOGE"):
        price, out = 100.0, []
        for i in range(12 * 36):
            o = price
            price *= 1 + rng.gauss(0.0002 if name != "DOGE" else -0.0002, 0.004)
            out.append(Candle(start + i * il.STEP, o, max(o, price) * 1.001, min(o, price) * 0.999, price, 1e9))
        series[name] = out
    begin, end = start + timedelta(hours=8), start + timedelta(hours=35)
    bt = il.backtest_engine(kind, series, begin, end, tmp_path / "bt.sqlite")
    engine = il.open_account(tmp_path / "live.sqlite", None, begin)
    chosen = [m for m in il.markets(crypto_only=True) if m.name in series]
    t = begin
    try:
        while t <= end:
            window = {n: [c for c in v if c.open_time + il.STEP <= t] for n, v in series.items()}
            il.strategy_cycle(engine, kind, window, chosen, t)
            t += timedelta(minutes=10)
        live = [(f["symbol"], f["time"], round(f["quantity"], 6), round(f["price"], 6), f["reason"]) for f in engine.fills()]
    finally:
        engine.close()
    back = il.open_account(tmp_path / "bt.sqlite", None, begin)
    try:
        sim = [(f["symbol"], f["time"], round(f["quantity"], 6), round(f["price"], 6), f["reason"]) for f in back.fills()]
    finally:
        back.close()
    assert live and sim == live and bt["tranzactii"] == len(live)


def test_diagnostic_pe_motive(tmp_path):
    """Punctul 1 din auditul din 5.11: piețele cu țintă care nu pot primi ordin, raportate separat pe motive."""
    by = {m.name: m for m in il.markets()}
    engine = il.open_account(tmp_path / "d.sqlite", None, T0)
    sunday = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)          # duminică: bursele închise, crypto deschis
    try:
        for name in ("AAPL", "BITCOIN", "RHEINMETALL"):
            engine.register_instrument(il.paper_runner.instrument_for(by[name]))
        engine.on_bar("AAPL", _bars(1, start=sunday - timedelta(days=2))[0])
        engine.on_bar("BITCOIN", _bars(1, start=sunday - timedelta(hours=2))[0])
        daily = {"AAPL": _bars(30), "BITCOIN": _bars(30), "NVDA": _bars(30)}
        d = il.diagnose(engine, {"AAPL": 0.1, "BITCOIN": 0.1, "RHEINMETALL": 0.1, "NVDA": -0.1, "KO": 0.0}, daily, by,
                        sunday)
    finally:
        engine.close()
    assert d == {"fara_istoric_zilnic": ["RHEINMETALL"], "fara_lumanari_intraday": ["NVDA"],
                 "bursa_inchisa": ["AAPL"], "date_vechi": ["BITCOIN"]}
    assert il.session(by["RHEINMETALL"]) == "xetra" and il.session(by["BAE"]) == "lse"
    assert il.session(by["EURUSD"]) == "forex" and il.session(by["DOGE"]) == "crypto"


def test_actiunile_si_apararea_primesc_ordine(tmp_path, monkeypatch):
    """Criteriul de acceptare al punctului 1: țintă nenulă + istoric zilnic + lumânări intraday recente = ordin,
    inclusiv la acțiuni (AAPL) și apărare (RHEINMETALL)."""
    monkeypatch.setenv("BND_TRADING_MODE", "PAPER")
    _run(tmp_path, il.TWIN_OF)
    settings, _ = il.p24_state(tmp_path / il.TWIN_OF / "paper.sqlite")
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    daily = {n: _bars(40, start=now - timedelta(days=41), step=lambda i: 0.002 if i % 2 else -0.0015)
             for n in ("AAPL", "RHEINMETALL")}
    bars = {n: _bars(30, start=now - timedelta(minutes=5 * 31)) for n in ("AAPL", "RHEINMETALL")}
    report = {"time": now.isoformat(), "weights_base": {"AAPL": 0.1, "RHEINMETALL": -0.1}, "signals": {}}
    engine = il.open_account(tmp_path / "twin.sqlite", settings, now)
    try:
        out = il.twin_cycle(engine, settings, report, daily, bars, il.markets(), now)
    finally:
        engine.close()
    assert sorted(o["market"] for o in out["orders"]) == ["AAPL", "RHEINMETALL"]
    assert not any(out["diagnostic"].values())


def test_backtest_raporteaza_oprirea_de_siguranta(tmp_path):
    import random
    rng = random.Random(3)
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    bars = {}
    for n in [m.name for m in il.markets(True)][:8]:
        p, out = 100.0, []
        for i in range(288 * 4):
            o = p
            p *= 1 + rng.gauss(0, 0.004) * (6 if 600 < i < 700 else 1)
            out.append(Candle(start + i * il.STEP, o, max(o, p) * 1.001, min(o, p) * 0.999, p, 1e9))
        bars[n] = out
    a = il.backtest_engine(il.TREND, bars, start + timedelta(days=1), start + timedelta(days=4), tmp_path / "a.sqlite")
    b = il.backtest_engine(il.TREND, bars, start + timedelta(days=1), start + timedelta(days=4), tmp_path / "b.sqlite",
                           safety=False)
    assert a["oprit_de_siguranta"] and "Daily loss" in a["motiv_oprire"]
    assert not b["oprit_de_siguranta"] and b["tranzactii"] > a["tranzactii"]
