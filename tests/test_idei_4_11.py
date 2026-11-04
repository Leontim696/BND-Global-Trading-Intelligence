"""Cele patru idei din 4.11: frâna la pierderi, contra mulțimii (funding), prudența la anunțuri, meta-formația."""

import json
from datetime import datetime, timedelta, timezone

from src.bnd import formations as fm, paper_runner
from src.bnd.paper_engine import PaperEngine


def _data(tmp_path):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows, price = ["open_time,open,high,low,close,volume"], 100.0
    for i in range(300):
        price *= 1.012 if i % 2 else 0.995
        rows.append(f"{(today - timedelta(days=301 - i)).isoformat()},{price},{price * 1.01},{price * 0.99},{price},1000")
    data = tmp_path / "data"; data.mkdir()
    (data / "GOLD.csv").write_text("\n".join(rows) + "\n")
    (tmp_path / "s.json").write_text(json.dumps({"signals": {"GOLD": 1.0}}))
    return data


def _run(tmp_path, key, extra=()):
    by = {f["key"]: f for f in fm.FORMATIONS}
    out = tmp_path / f"{key}.json"
    args = ["--state", str(tmp_path / key / "paper.sqlite"), "--data-dir", str(_data(tmp_path)) if not (tmp_path / "data").exists() else str(tmp_path / "data"),
            "--signals", str(tmp_path / "s.json"), "--capital", "11183", "--universe", "unic",
            "--strategy", by[key]["strategy"], "--json", str(out), *by[key].get("settings", fm.STANDARD).split(), *extra]
    assert paper_runner.main(args) == 0
    return json.loads(out.read_text())


def test_prudenta_la_anunturi_injumatateste_expunerea(tmp_path, monkeypatch):
    monkeypatch.setenv("BND_TRADING_MODE", "PAPER")
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
    cal = tmp_path / "economic.csv"
    cal.write_text("id,time_utc,country,title,impact,forecast,previous\n"
                   f"x,{tomorrow}T13:30+00:00,USD,Non-Farm Employment Change,High,,\n"
                   f"y,{tomorrow}T10:00+00:00,EUR,ECB,High,,\n")
    base = _run(tmp_path, "p16-frana-pierderi")
    cut = _run(tmp_path, "p18-prudenta-anunturi", ["--events", str(cal)])
    assert cut["events_tomorrow"] == ["Non-Farm Employment Change"] and cut["exposure_scale"] == 0.5
    assert abs(cut["weights"]["GOLD"] - 0.5 * base["weights"]["GOLD"]) < 1e-6
    assert base["brake"] is False and base["exposure_scale"] == 1.0


def test_load_events_doar_sua_high():
    assert paper_runner.load_events(None) == ()


def test_frana_la_pierderi(tmp_path, monkeypatch):
    monkeypatch.setenv("BND_TRADING_MODE", "PAPER")
    first = _run(tmp_path, "p16-frana-pierderi")
    engine = PaperEngine.open(tmp_path / "p16-frana-pierderi" / "paper.sqlite")
    try:
        engine._db.execute("UPDATE account SET peak_equity = ?", (11183 / 0.95,))   # contul e acum cu 5% sub vârf
        engine._db.commit()
    finally:
        engine.close()
    by = {f["key"]: f for f in fm.FORMATIONS}
    out = tmp_path / "second.json"
    assert paper_runner.main(["--state", str(tmp_path / "p16-frana-pierderi" / "paper.sqlite"), "--data-dir",
                              str(tmp_path / "data"), "--signals", str(tmp_path / "s.json"), "--strategy", "hibrid",
                              "--json", str(out)]) == 0
    second = json.loads(out.read_text())
    assert second["brake"] is True and second["exposure_scale"] == 0.5
    assert first["brake"] is False


def test_funding_contra_multimii(tmp_path):
    assert fm.funding_clip(1.0, 0.0005) == 0.0 and fm.funding_clip(-1.0, 0.0005) == -1.0
    assert fm.funding_clip(-1.0, -0.0001) == 0.0 and fm.funding_clip(0.5, 0.0001) == 0.5
    assert fm.funding_clip(0.7, None) == 0.7
    d = tmp_path / "funding"; d.mkdir()
    (d / "BITCOIN.csv").write_text("time,rate,source\nt1,0.0001,okx\nt2,0.0004,okx\nt3,0.0005,okx\nt4,0.0006,okx\n")
    assert abs(fm.load_funding(d)["BITCOIN"] - 0.0005) < 1e-12
    f = {x["key"]: x for x in fm.FORMATIONS}["p17-contra-funding"]
    votes = {"BITCOIN": dict.fromkeys(fm.AGENTS, "BUY")}
    out = fm.signals_for(f, votes, {}, {"BITCOIN": 1.0, "GOLD": -0.5}, {"BITCOIN": 0.0005})
    assert out == {"BITCOIN": 0.0, "GOLD": -0.5}          # long blocat pe BTC; GOLD doar regula


def test_meta_alege_cele_mai_bune_3(tmp_path):
    now = datetime(2026, 11, 10, 22, 0, tzinfo=timezone.utc)
    for i, key in enumerate(fm.META_POOL[:5]):
        path = tmp_path / key / "paper.sqlite"
        path.parent.mkdir(parents=True)
        engine = PaperEngine.create(path, 11183.0, currency="USD", now=now - timedelta(days=5))
        engine.record("daily_run", {"time": (now - timedelta(days=4)).isoformat(), "equity": 11183.0}, now)
        engine.record("daily_run", {"time": now.isoformat(), "equity": 11183.0 + 10 * i}, now)
        engine.close()
    top = fm.meta_top(tmp_path, "2026-11-10")
    assert top == list(fm.META_POOL[2:5])[::-1]
    assert fm.meta_top(None, "2026-11-10") is None
    f = {x["key"]: x for x in fm.FORMATIONS}["p19-meta-top3"]
    votes = {"BITCOIN": {"gpt": "BUY"}}
    assert fm.signals_for(f, votes, dict.fromkeys(fm.AGENTS, 1.0)) == {"BITCOIN": 0.5}   # fără clasament: tot consiliul


def test_idee_nebuna_combina_toate_regulile(tmp_path, monkeypatch):
    monkeypatch.setenv("BND_TRADING_MODE", "PAPER")
    f = {x["key"]: x for x in fm.FORMATIONS}["p20-idee-nebuna"]
    assert f["kind"] == "funding" and f["strategy"] == "ai_council"
    for flag in ("--take-profit-pct 5", "--recycle reciclare", "--dd-brake-pct 3", "--event-cut 0.5", "--max-leverage 2"):
        assert flag in f["settings"]
    r = _run(tmp_path, "p20-idee-nebuna")
    s = r["settings"]
    assert s["take_profit_pct"] == 5 and s["recycle"] == "reciclare" and s["dd_brake_pct"] == 3 and s["event_cut"] == 0.5
    assert r["recycling"]["mode"] == "reciclare" and r["exposure_scale"] == 1.0
