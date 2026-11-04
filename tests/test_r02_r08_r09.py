"""R02 (independența AI), R08 (gemeni cu execuție mai proastă), R09 (alfa negativ) — fără apeluri AI."""

import sqlite3

from src.bnd import formations as fm, ortogonalitate as og, paper_runner
from src.bnd.decision_registry import SCHEMA
from src.bnd.universe import select


def _reg(path, rows):
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    for did, sym, outcome, votes in rows:
        db.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,'{\"complete\": true}')",
                   (did, did[:10], sym, 100.0, 5, "HOLD", "r", 0, "x" if outcome is not None else None,
                    None, outcome))
        for agent, vote in votes.items():
            db.execute("INSERT INTO votes VALUES (?,?,?,?,?)", (did, agent, "final", vote, 0.6))
    db.commit()
    db.close()


def test_r02_ai_identice_valoreaza_cat_unul(tmp_path):
    reg = tmp_path / "r.sqlite"
    rows = []
    for i in range(40):
        v = ["BUY", "SELL", "HOLD"][i % 3]
        rows.append((f"2026-11-0{1 + i % 3}:M{i}", f"M{i}", 0.01 if v == "BUY" else -0.01, dict.fromkeys(fm.AGENTS, v)))
    _reg(reg, rows)
    r = og.analyse(str(reg))
    assert r["decizii"] == 40 and r["ai_independente_efectiv"] == 1.0
    assert r["perechi"]["gpt-grok"]["acord"] == 1.0 and r["perechi"]["gpt-grok"]["kappa"] == 1.0
    assert r["contributie"]["fara_gpt"]["directie_schimbata_pct"] == 0.0


def test_r09_doar_decizii_incheiate_si_ambele_jumatati(tmp_path):
    reg = tmp_path / "r.sqlite"
    rows = []
    for i in range(80):
        day = "2026-11-01" if i < 40 else "2026-11-20"
        votes = dict.fromkeys(fm.AGENTS, "HOLD")
        votes["deepseek"] = "BUY"
        rows.append((f"{day}:M{i}", f"M{i}", -0.02, votes))          # deepseek greșește mereu
    _reg(reg, rows)
    r = og.analyse(str(reg))["alfa_negativ"]["agenti"]
    assert r["deepseek"]["candidat_inversare"] is True
    assert r["gpt"]["candidat_inversare"] is False and r["gpt"]["motiv"] == "prea puține voturi"


def test_r08_costuri_dublate_si_ordine_ratate_deterministe():
    from datetime import datetime, timezone
    market = select([], [], "unic")[0]
    base, twin = paper_runner.instrument_for(market), paper_runner.instrument_for(market, 2.0)
    assert abs(twin.fee_pct - 2 * base.fee_pct) < 1e-12 and abs(twin.slippage_pct - 2 * base.slippage_pct) < 1e-12
    now = datetime(2026, 11, 5, 22, 50, tzinfo=timezone.utc)
    names = [f"M{i}" for i in range(2000)]
    skipped = [n for n in names if paper_runner._skipped(n, now, 20)]
    assert 300 < len(skipped) < 500                                  # ~20%
    assert skipped == [n for n in names if paper_runner._skipped(n, now, 20)]   # mereu aceleași


def test_r08_intarziere_foloseste_voturile_de_ieri(tmp_path):
    reg = tmp_path / "r.sqlite"
    _reg(reg, [("2026-11-04:BITCOIN", "BITCOIN", None, dict.fromkeys(fm.AGENTS, "SELL")),
               ("2026-11-05:BITCOIN", "BITCOIN", None, dict.fromkeys(fm.AGENTS, "BUY"))])
    out = fm.build_all(str(reg), ["BITCOIN"], "2026-11-05")
    assert out["p23-geaman-intarziere"]["signals"] == {"BITCOIN": -1.0}
    assert out["p5-gpt-claude-grok"]["signals"] == {"BITCOIN": 1.0}
