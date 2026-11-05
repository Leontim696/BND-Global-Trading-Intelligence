"""Formații AI: semnale din voturile deja salvate, fără apeluri AI."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.bnd import dashboard, formations as fm
from src.bnd.decision_registry import SCHEMA
from src.bnd.paper_engine import PaperEngine

DAY = "2026-11-04"


def _registry(path, votes):
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    for coin, by_agent in votes.items():
        db.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,NULL,NULL,NULL,'{}')",
                   (f"{DAY}:{coin}", DAY, coin, 1.0, 5, "HOLD", "r", 0))
        for agent, stages in by_agent.items():
            for stage, vote in stages.items():
                db.execute("INSERT INTO votes VALUES (?,?,?,?,?)", (f"{DAY}:{coin}", agent, stage, vote, 0.6))
    db.commit()
    db.close()


def test_14_formatii_cu_strategii_corecte():
    assert len(fm.FORMATIONS) == 39
    assert len({f["key"] for f in fm.FORMATIONS}) == 39
    by = {f["key"]: f for f in fm.FORMATIONS}
    assert by["p1-gpt-grok"]["strategy"] == "hibrid" and by["p2-gpt-grok-liber"]["strategy"] == "ai_council"
    assert by["p5-gpt-claude-grok"]["members"] == ("gpt", "claude", "grok")
    assert sum(f["point"] == 3 for f in fm.FORMATIONS) == 5 and sum(f["point"] == 4 for f in fm.FORMATIONS) == 5


def test_prag_si_semnal():
    assert [fm.threshold(n) for n in (1, 2, 3, 5)] == [1, 1, 1, 2]
    five = fm.AGENTS
    # cu 5 membri: exact formula contului unic (1 vot net = 0,5; 2+ = 1)
    assert fm.formation_signal({"gpt": "BUY"}, five) == 0.5
    assert fm.formation_signal({"gpt": "SELL", "grok": "SELL"}, five) == -1.0
    assert fm.formation_signal({"gpt": "BUY"}, ("gpt",)) == 1.0
    assert fm.formation_signal({"gpt": "BUY", "grok": "SELL"}, ("gpt", "grok")) == 0.0
    assert fm.formation_signal({"claude": "SELL", "gemini": "BUY"}, ("gpt", "grok")) == 0.0   # doar membrii contează


def test_votul_final_are_prioritate_si_piata_fara_decizie_lipseste(tmp_path):
    reg = tmp_path / "registry.sqlite"
    _registry(reg, {"BITCOIN": {"gpt": {"initial": "BUY", "final": "SELL"}, "grok": {"initial": "SELL"}}})
    result = fm.build_all(str(reg), ["BITCOIN", "GOLD"], DAY)
    assert result["p3-gpt"]["signals"] == {"BITCOIN": -1.0}
    assert result["p1-gpt-grok"]["signals"] == {"BITCOIN": -1.0}
    assert result["p3-claude"]["signals"] == {"BITCOIN": 0.0}
    assert result["p3-gpt"]["missing"] == ["GOLD"]


def test_cli_scrie_un_fisier_pe_formatie(tmp_path):
    reg = tmp_path / "registry.sqlite"
    _registry(reg, {"BITCOIN": {"grok": {"final": "BUY"}}})
    assert fm.main(["--registry", str(reg), "--coins", "BITCOIN", "--day", DAY, "--out-dir", str(tmp_path / "s")]) == 0
    files = sorted(p.name for p in (tmp_path / "s").iterdir())
    assert len(files) == 39
    assert json.loads((tmp_path / "s" / "p4-grok-liber.json").read_text())["signals"] == {"BITCOIN": 1.0}


def test_list_pentru_workflow(capsys):
    assert fm.main(["--list"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 39 and lines[0].split("\t")[:2] == ["p1-gpt-grok", "hibrid"]


def test_dashboard_citeste_formatiile(tmp_path):
    now = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    (tmp_path / "p3-gpt").mkdir()
    PaperEngine.create(tmp_path / "p3-gpt" / "paper.sqlite", 11_183.0, currency="USD", now=now).close()
    rows = dashboard.read_formations(tmp_path)
    assert len(rows) == 39
    gpt = next(r for r in rows if r["key"] == "p3-gpt")
    assert gpt["exists"] and gpt["equity"] == 11_183.0 and gpt["positions"] == 0
    assert sum(r["exists"] for r in rows) == 1
    assert dashboard.read_formations(None) == []


def test_workflow_fara_apeluri_ai_si_ramura_protejata():
    wf = Path(".github/workflows/formatii-ai.yml").read_text()
    assert 'BND_ALLOW_LIVE_AI: "false"' in wf and "src.bnd.formations" in wf
    assert "OPENROUTER" not in wf and "secrets." not in wf
    assert "formatii-ai" in Path(".github/workflows/branch-cleanup.yml").read_text()
    assert "--formations out/f" in Path(".github/workflows/preturi-live.yml").read_text()


def test_sablonul_are_fila_formatii():
    t = Path("src/bnd/dashboard_template.html").read_text()
    assert '["formatii","Formații AI"]' in t and 'key === "formatii" ? formationsView()' in t


def test_p7_ponderi_egale_dau_formula_contului_unic_si_ponderile_conteaza():
    equal = dict.fromkeys(fm.AGENTS, 1.0)
    for votes in ({"gpt": "BUY"}, {"gpt": "SELL", "grok": "SELL"}, {"gpt": "BUY", "claude": "SELL"}, {}):
        assert fm.weighted_signal(votes, equal) == fm.formation_signal(votes, fm.AGENTS)
    only_gpt = {**dict.fromkeys(fm.AGENTS, 0.0), "gpt": 1.0}
    assert fm.weighted_signal({"gpt": "BUY", "grok": "SELL", "claude": "SELL"}, only_gpt) == 1.0


def test_p7_ponderi_din_decizii_incheiate_doar_din_trecut(tmp_path):
    reg = tmp_path / "registry.sqlite"
    _registry(reg, {})
    db = sqlite3.connect(reg)
    for i in range(25):
        did = f"2026-10-{1 + i % 28:02d}:M{i}"
        db.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,'{}')",
                   (did, "2026-10-01", f"M{i}", 1.0, 5, "HOLD", "r", 0, "2026-10-30T00:00:00", 1.1, 0.1))
        for a in fm.AGENTS:   # gpt ghicește mereu, deepseek greșește mereu, ceilalți 60%
            vote = {"gpt": "BUY", "deepseek": "SELL"}.get(a, "BUY" if i % 5 < 3 else "SELL")
            db.execute("INSERT INTO votes VALUES (?,?,?,?,?)", (did, a, "final", vote, 0.6))
    db.commit(); db.close()
    w = fm.agent_weights(str(reg), "2026-11-04")
    assert w["gpt"] == 0.5 and w["deepseek"] == 0.0 and abs(w["grok"] - 0.1) < 1e-9
    assert fm.agent_weights(str(reg), "2026-10-29") == dict.fromkeys(fm.AGENTS, 1.0)   # încă neîncheiate atunci


def test_p8_consens_si_p9_doar_crypto():
    by = {f["key"]: f for f in fm.FORMATIONS}
    votes = {"BITCOIN": dict.fromkeys(("gpt", "grok", "claude", "gemini"), "SELL"),
             "GOLD": {"gpt": "SELL", "grok": "SELL", "claude": "SELL"},
             "DOGE": {"gpt": "BUY", "grok": "BUY"}}
    equal = dict.fromkeys(fm.AGENTS, 1.0)
    assert fm.signals_for(by["p8-consens"], votes, equal) == {"BITCOIN": -1.0}
    assert fm.signals_for(by["p9-doar-crypto"], votes, equal) == {"BITCOIN": -1.0, "DOGE": 1.0}


def test_scor_provizoriu_din_voturi(tmp_path):
    reg = tmp_path / "registry.sqlite"
    _registry(reg, {"BITCOIN": {"gpt": {"final": "SELL"}}, "GOLD": {"gpt": {"final": "BUY"}}})
    by = {f["key"]: f for f in fm.FORMATIONS}
    s = fm.vote_score(str(reg), {"BITCOIN": [0.9, "t"], "GOLD": [0.95, "t"]}, by["p3-gpt"])
    assert s["calls"] == 2 and s["hit_rate"] == 0.5 and abs(s["mean_pct"] - 2.5) < 1e-9
    assert fm.vote_score(None, {}, by["p3-gpt"]) is None


def test_coloana_agresiv_leverage_si_lichidare(tmp_path):
    reg = tmp_path / "registry.sqlite"
    _registry(reg, {"BITCOIN": {"gpt": {"final": "SELL"}}, "GOLD": {"gpt": {"final": "BUY"}}})
    by = {f["key"]: f for f in fm.FORMATIONS}
    # BITCOIN −10% (SELL câștigă 10%), GOLD −5% (BUY pierde 5%)
    s = fm.vote_score(str(reg), {"BITCOIN": [0.9, "t"], "GOLD": [0.95, "t"]}, by["p3-gpt"])
    assert s["pnl"]["1"] == 5.0                       # +10 − 5
    assert s["pnl"]["2"] == 10.0                      # +20 − 10
    assert s["pnl"]["5"] == 25.0                      # +50 − 25
    assert s["pnl"]["10"] == 50.0                     # +100 − 50 (−5% nu atinge pragul de lichidare de −9%)
    assert s["liquidated"] == {"2": 0, "5": 0, "10": 0}
    s = fm.vote_score(str(reg), {"BITCOIN": [0.9, "t"], "GOLD": [0.85, "t"]}, by["p3-gpt"])
    assert s["liquidated"]["10"] == 1 and s["pnl"]["10"] == 0.0     # +100 pe BTC, −100 (lichidat) pe GOLD
    assert s["liquidated"]["5"] == 0 and s["pnl"]["5"] == -25.0     # +50 − 75


def test_p10_miza_dupa_convingere():
    four_sell = dict.fromkeys(("gpt", "grok", "claude", "gemini"), "SELL")
    assert fm.conviction_signal(four_sell, -1.0) == -1.0          # puternic: 4/5 + regula la fel
    assert fm.conviction_signal(four_sell, 0.0) == -0.5           # regula neutră: mediu
    assert fm.conviction_signal(four_sell, 1.0) == 0.0            # contradictoriu: nimic
    assert fm.conviction_signal({"gpt": "BUY", "grok": "BUY"}, 0.6) == 0.5     # 2 net + regula la fel: mediu
    assert fm.conviction_signal({"gpt": "BUY"}, 1.0) == 0.0       # slab: 1 vot net
    assert fm.conviction_signal(four_sell, None) == 0.0           # fără regulă, fără poziție nouă
    by = {f["key"]: f for f in fm.FORMATIONS}
    assert by["p10-convingere"]["strategy"] == "ai_council"
    out = fm.signals_for(by["p10-convingere"], {"BITCOIN": four_sell, "GOLD": four_sell}, {}, {"BITCOIN": -1.0})
    assert out == {"BITCOIN": -1.0}                               # GOLD fără semnalul regulii: poziția rămâne cum e


def test_semnalul_regulii_din_lumanari_ca_in_contul_unic(tmp_path):
    from datetime import timedelta
    from src.bnd.paper_runner import latest_weights, _make_factory
    from src.bnd.portfolio import PortfolioConfig
    from src.bnd.market_data import load_csv
    from src.bnd.universe import select
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = ["open_time,open,high,low,close,volume"]
    price = 100.0
    for i in range(300):           # urcare constantă: regula trebuie să dea semnal pozitiv
        price *= 1.004 if i % 7 else 0.99
        t = (start + timedelta(days=i)).isoformat()
        rows.append(f"{t},{price},{price * 1.01},{price * 0.99},{price},1000")
    (tmp_path / "GOLD.csv").write_text("\n".join(rows) + "\n")
    got = fm.rule_signals(tmp_path, ["GOLD", "SILVER"])
    assert list(got) == ["GOLD"] and got["GOLD"] > 0
    market = [m for m in select([], [], "unic") if m.name == "GOLD"]
    data = {"GOLD": load_csv(tmp_path / "GOLD.csv")}
    _, ref = latest_weights(data, market, _make_factory({"strategy": "hibrid", "param": [], "members": None}, data),
                            PortfolioConfig())
    assert got["GOLD"] == ref["GOLD"]


def test_p11_agresiv_se_poate_crea_si_respecta_plafonul(tmp_path, monkeypatch):
    from datetime import timedelta
    from src.bnd import paper_runner
    monkeypatch.setenv("BND_TRADING_MODE", "PAPER")
    by = {f["key"]: f for f in fm.FORMATIONS}
    agr = by["p11-convingere-agresiv"]
    assert agr["kind"] == "convingere" and "--max-leverage 3" in agr["settings"]
    assert "settings" not in by["p10-convingere"]                     # P10 rămâne standard
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows, price = ["open_time,open,high,low,close,volume"], 100.0
    for i in range(300):
        price *= 1.003
        rows.append(f"{(start + timedelta(days=i)).isoformat()},{price},{price * 1.01},{price * 0.99},{price},1000")
    data = tmp_path / "data"; data.mkdir()
    (data / "GOLD.csv").write_text("\n".join(rows) + "\n")
    (tmp_path / "s.json").write_text(json.dumps({"signals": {"GOLD": 1.0}}))
    code = paper_runner.main(["--state", str(tmp_path / "a" / "paper.sqlite"), "--data-dir", str(data),
                              "--signals", str(tmp_path / "s.json"), "--capital", "11183", "--universe", "unic",
                              "--strategy", "ai_council", *agr["settings"].split()])
    assert code == 0
    engine = PaperEngine.open(tmp_path / "a" / "paper.sqlite")
    try:
        assert engine.journal("runner_settings")[-1]["payload"]["max_leverage"] == 3.0
    finally:
        engine.close()


def test_instantaneu_orar(tmp_path):
    now = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    (tmp_path / "f" / "p3-gpt").mkdir(parents=True)
    PaperEngine.create(tmp_path / "f" / "p3-gpt" / "paper.sqlite", 11_183.0, currency="USD", now=now).close()
    (tmp_path / "q.json").write_text(json.dumps({"time": "t", "quotes": {}}))
    assert fm.main(["--snapshot", str(tmp_path / "f"), "--quotes", str(tmp_path / "q.json"),
                    "--out", str(tmp_path / "s.json")]) == 0
    rows = json.loads((tmp_path / "s.json").read_text())
    assert len(rows) == 1 and rows[0]["key"] == "p3-gpt" and rows[0]["value"] == 11183.0 and rows[0]["pnl"] == 0.0
    line = (tmp_path / "s.csv").read_text().strip().split(",")
    assert line[1] == "p3-gpt" and len(line) == len(fm.CSV_COLUMNS)


def test_p12_take_profit_si_stop_fix_pe_ordine(tmp_path, monkeypatch):
    from datetime import timedelta
    from src.bnd import paper_runner
    monkeypatch.setenv("BND_TRADING_MODE", "PAPER")
    by = {f["key"]: f for f in fm.FORMATIONS}
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=301)
    rows, price = ["open_time,open,high,low,close,volume"], 100.0
    for i in range(300):
        price *= 1.012 if i % 2 else 0.995
        rows.append(f"{(start + timedelta(days=i)).isoformat()},{price},{price * 1.01},{price * 0.99},{price},1000")
    data = tmp_path / "data"; data.mkdir()
    (data / "GOLD.csv").write_text("\n".join(rows) + "\n")
    (tmp_path / "s.json").write_text(json.dumps({"signals": {"GOLD": 1.0}}))
    out = tmp_path / "r.json"
    assert paper_runner.main(["--state", str(tmp_path / "a" / "paper.sqlite"), "--data-dir", str(data),
                              "--signals", str(tmp_path / "s.json"), "--capital", "11183", "--universe", "unic",
                              "--strategy", "hibrid", "--json", str(out),
                              *by["p12-tp5-sl1"]["settings"].split()]) == 0
    order = json.loads(out.read_text())["orders"][0]
    assert order["side"] == "BUY"
    assert abs(order["take_profit"] / price - 1.05) < 1e-9 and abs(order["stop_loss"] / price - 0.99) < 1e-9


def test_conturile_vechi_raman_cu_stop_atr():
    from src.bnd.paper_runner import _config, DEFAULTS
    old = {k: v for k, v in DEFAULTS.items() if k not in ("stop_pct", "take_profit_pct")}
    cfg = _config(old)
    assert cfg.stop_pct is None and cfg.take_profit_pct is None and cfg.stop_atr == 3.0


def test_p15_reciclare_ruleaza_in_runner(tmp_path, monkeypatch):
    from datetime import timedelta
    from src.bnd import paper_runner
    monkeypatch.setenv("BND_TRADING_MODE", "PAPER")
    by = {f["key"]: f for f in fm.FORMATIONS}
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows, price = ["open_time,open,high,low,close,volume"], 100.0
    for i in range(300):
        price *= 1.012 if i % 2 else 0.995
        rows.append(f"{(today - timedelta(days=301 - i)).isoformat()},{price},{price * 1.01},{price * 0.99},{price},1000")
    data = tmp_path / "data"; data.mkdir()
    (data / "GOLD.csv").write_text("\n".join(rows) + "\n")
    (tmp_path / "s.json").write_text(json.dumps({"signals": {"GOLD": 1.0}}))
    out = tmp_path / "r.json"
    assert paper_runner.main(["--state", str(tmp_path / "a" / "paper.sqlite"), "--data-dir", str(data),
                              "--signals", str(tmp_path / "s.json"), "--capital", "11183", "--universe", "unic",
                              "--strategy", "hibrid", "--json", str(out),
                              *by["p15-tp-reciclare"]["settings"].split()]) == 0
    report = json.loads(out.read_text())
    assert report["recycling"]["mode"] == "reciclare" and report["recycling"]["freed"] == 0.0
    assert report["settings"]["recycle"] == "reciclare"
