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
    assert len(fm.FORMATIONS) == 17
    assert len({f["key"] for f in fm.FORMATIONS}) == 17
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
    assert len(files) == 17
    assert json.loads((tmp_path / "s" / "p4-grok-liber.json").read_text())["signals"] == {"BITCOIN": 1.0}


def test_list_pentru_workflow(capsys):
    assert fm.main(["--list"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 17 and lines[0].split("\t")[:2] == ["p1-gpt-grok", "hibrid"]


def test_dashboard_citeste_formatiile(tmp_path):
    now = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    (tmp_path / "p3-gpt").mkdir()
    PaperEngine.create(tmp_path / "p3-gpt" / "paper.sqlite", 11_183.0, currency="USD", now=now).close()
    rows = dashboard.read_formations(tmp_path)
    assert len(rows) == 17
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
