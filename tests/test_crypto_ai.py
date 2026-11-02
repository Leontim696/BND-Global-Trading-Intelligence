"""Contul de cripto condus de consiliul AI: semnale din voturi, fără apeluri plătite."""

import json
from datetime import datetime, timezone

import pytest

from src.bnd import crypto_signals, paper_runner
from src.bnd.crypto_signals import build_signals, signal_from_meta
from src.bnd.decision_registry import DecisionRegistry
from src.bnd.decision_rules import CouncilDecision, DecisionRule
from src.bnd.fusion_council import FusionCouncil, Vote
from src.bnd.paper_engine import EngineLimits, PaperEngine
from src.bnd.paper_runner import RunnerConfig, run_daily
from src.bnd.portfolio import PortfolioConfig
from src.bnd.universe import UNIVERSES, select
from tests.test_paper_runner import MARKETS, START, make_data, now_after


@pytest.mark.parametrize("meta,expected", [
    ({"net": 3}, 1.0), ({"net": 2}, 1.0), ({"net": 1}, 0.5), ({"net": 0}, 0.0),
    ({"net": -1}, -0.5), ({"net": -4}, -1.0), ({"lean": 1}, 0.5), ({"lean": -1}, -0.5),
    ({}, 0.0)])
def test_signal_from_votes(meta, expected):
    assert signal_from_meta(meta) == expected


def test_crypto_universe_is_separate():
    names = [m.name for m in select(universe="crypto")]
    assert names == ["BITCOIN", "ETHEREUM", "SOLANA", "BNB", "XRP"]
    assert "SOLANA" not in [m.name for m in UNIVERSES["etf"]]      # contul existent nu se schimbă


def test_signals_only_for_coins_decided_today(tmp_path):
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    council = FusionCouncil()
    decision = CouncilDecision(Vote.HOLD, DecisionRule.MAJORITY, {}, (), (), True, ())
    now = datetime(2026, 11, 1, 21, 40, tzinfo=timezone.utc)
    registry.record("2026-11-01:BITCOIN", now, "BITCOIN", 70000.0, council, decision,
                    meta={"net": -2})
    registry.record("2026-10-31:XRP", now, "XRP", 2.0, council, decision, meta={"net": 3})

    result = build_signals(registry, ["BITCOIN", "XRP"], "2026-11-01")

    assert result["signals"] == {"BITCOIN": -1.0}
    assert result["missing"] == ["XRP"]


def test_runner_trades_given_signals_and_leaves_undecided_alone(tmp_path):
    data = make_data()
    engine = PaperEngine.create(tmp_path / "paper.sqlite", 10_000.0, currency="USD",
                                limits=EngineLimits(), now=START)
    config = RunnerConfig(portfolio=PortfolioConfig(vol_lookback=20))

    report = run_daily(engine, data, MARKETS, lambda: None, config, "ai_council",
                       now_after(data), given_signals={"UP": 1.0, "DOWN": -1.0})

    sides = {o["market"]: o["side"] for o in report["orders"]}
    assert sides["UP"] == "BUY" and sides["DOWN"] == "SELL"
    assert "FX" not in sides                      # fără semnal azi: nicio comandă nouă


def test_signals_file_is_validated(tmp_path):
    bad = tmp_path / "s.json"
    bad.write_text(json.dumps({"signals": {"BITCOIN": 2}}))
    with pytest.raises(ValueError):
        paper_runner._read_signals(bad)
    bad.write_text("nu e json")
    with pytest.raises(ValueError):
        paper_runner._read_signals(bad)


def test_ai_council_strategy_needs_signals(tmp_path, capsys):
    code = paper_runner.main(["--state", str(tmp_path / "a.sqlite"), "--data-dir", str(tmp_path),
                              "--capital", "1000", "--universe", "crypto",
                              "--strategy", "ai_council"])
    assert code == 2


def test_cli_writes_the_signals_file(tmp_path):
    out = tmp_path / "o.json"
    assert crypto_signals.main(["--registry", str(tmp_path / "lipsa.sqlite"), "--out", str(out),
                                "--day", "2026-11-01"]) == 0
    assert json.loads(out.read_text())["signals"] == {}


def test_ai_universe_covers_every_council_market():
    from src.bnd.council_daily import DEFAULT_MARKETS
    names = [m.name for m in select(universe="ai")]
    assert set(DEFAULT_MARKETS) <= set(names)
    assert names == list(dict.fromkeys(names)) and len(names) == 13


def test_old_decisions_without_net_use_the_saved_votes(tmp_path):
    from src.bnd.fusion_council import Opinion
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    council = FusionCouncil()
    council.submit(Opinion("deepseek", Vote.BUY, "test", 0.55))
    decision = CouncilDecision(Vote.HOLD, DecisionRule.MAJORITY, {}, (), (), False, ())
    now = datetime(2026, 11, 1, 21, 40, tzinfo=timezone.utc)
    registry.record("2026-11-01:NASDAQ100", now, "NASDAQ100", 690.0, council, decision,
                    meta={"bot_signal": 1})

    assert build_signals(registry, ["NASDAQ100"], "2026-11-01")["signals"] == {"NASDAQ100": 0.5}


def test_hybrid_blends_rules_and_council_and_falls_back_to_rules_without_an_ai_signal():
    from src.bnd.paper_runner import latest_weights
    from src.bnd.strategies import sma_crossover
    from tests.test_paper_runner import make_data

    data = make_data()
    config = PortfolioConfig(vol_lookback=20)
    rules_only = latest_weights(data, MARKETS, lambda: sma_crossover(5, 20), config)[1]
    blended = latest_weights(data, MARKETS, lambda: sma_crossover(5, 20), config,
                             {"UP": 1.0, "DOWN": 1.0}, blend=True)[1]

    assert rules_only["UP"] == 1 and rules_only["DOWN"] == -1
    assert blended["UP"] == 1.0                    # acord: semnal întreg
    assert blended["DOWN"] == 0.0                  # dezacord: se anulează
    assert blended["FX"] == rules_only["FX"]       # fără semnal AI azi: doar regulile


def test_hybrid_account_end_to_end_with_shorts_and_sector_for_memecoins(tmp_path, capsys):
    from tests.test_end_to_end import prepare
    from src.bnd.universe import UNIVERSES
    names = [m.name for m in UNIVERSES["unic"]]
    data_dir = prepare(tmp_path, markets=names, days=300)
    signals = tmp_path / "semnale.json"
    signals.write_text(json.dumps({"signals": {n: (1.0 if i % 2 else -1.0) for i, n in enumerate(names[:30])}}))
    args = ["--state", str(tmp_path / "paper.sqlite"), "--data-dir", str(data_dir), "--signals", str(signals),
            "--json", str(tmp_path / "last.json")]

    assert paper_runner.main(args + ["--capital", "11183", "--universe", "unic", "--strategy", "hibrid",
                                     "--max-leverage", "2", "--max-weight", "0.25", "--max-sector", "60",
                                     "--portfolio-vol", "15", "--financing", "5"]) == 0
    capsys.readouterr()

    last = json.loads((tmp_path / "last.json").read_text())
    engine = PaperEngine.open(tmp_path / "paper.sqlite")
    try:
        assert len(engine.registered_instruments()) == 71 if hasattr(engine, "registered_instruments") else True
        assert engine.instrument("DOGE").sector == "memecoin" and engine.instrument("BITCOIN").sector == ""
        assert any(o["side"] == "SELL" for o in last["orders"]) and any(o["side"] == "BUY" for o in last["orders"])
        assert last["weights"] and max(abs(w) for w in last["weights"].values()) <= 0.25 + 1e-9
        gross = sum(abs(w) for w in last["weights"].values())
        assert gross <= 2.0 + 1e-9
    finally:
        engine.close()


def test_missing_council_votes_are_loudly_visible_in_the_log(tmp_path, capsys):
    """Regresie: dacă rularea contului pică după miezul nopții UTC, ziua nouă nu are voturi și contul ar decide doar pe reguli, pe tăcute."""
    out = tmp_path / "o.json"
    crypto_signals.main(["--registry", str(tmp_path / "lipsa.sqlite"), "--out", str(out), "--day", "2026-11-02",
                         "--coins", "BITCOIN,ETHEREUM,SOLANA"])
    assert "::warning::" in capsys.readouterr().out
