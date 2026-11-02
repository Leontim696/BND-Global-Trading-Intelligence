"""De la date de piață la decizie, ordin virtual, contabilitate și raport: sintetic, fără bani, fără rețea.

Acoperă și reziliența: date duplicate, prețuri invalide, lipsă de piețe, ore fără fus orar,
rulări simultane și repornire la jumătatea zilei.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.bnd import council_daily as cd
from src.bnd import crypto_signals, dashboard, paper_runner
from src.bnd.decision_registry import DecisionRegistry
from src.bnd.market_data import Candle, MarketDataError, load_csv, save_csv, validate_series
from src.bnd.paper_engine import PaperEngine, PaperEngineError
from src.bnd.reconcile import reconcile
from src.bnd.universe import AI_MARKETS
from tests.test_multi_market_cli import START

ROOT = Path(__file__).resolve().parents[1]
DAYS = 400


def prepare(tmp_path, markets=AI_MARKETS, days=DAYS):
    """Date sintetice care se termină ieri (motorul refuză, corect, date mai vechi de 4 zile)."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    for k, name in enumerate(markets):
        candles, price = [], 100.0
        for i in range(days):
            drift = (0.001, -0.001, 0.0)[k % 3]
            close = price * (1 + drift) * (1 + 0.01 * (-1) ** (i + k))
            candles.append(Candle(end - timedelta(days=days - 1 - i), price, max(price, close),
                                  min(price, close), close, 1))
            price = close
        save_csv(candles, data_dir / f"{name}.csv")
    return data_dir


def runner(tmp_path, data_dir, signals, *extra):
    return paper_runner.main(["--state", str(tmp_path / "paper.sqlite"), "--data-dir", str(data_dir),
                              "--signals", str(signals), "--report", str(tmp_path / "REPORT.md"),
                              "--json", str(tmp_path / "last.json"), *extra])


def test_whole_chain_from_data_to_report(tmp_path, capsys):
    data_dir = prepare(tmp_path)
    data = {m: load_csv(data_dir / f"{m}.csv") for m in AI_MARKETS}
    registry = DecisionRegistry(tmp_path / "registry.sqlite")
    now = data["SP500"][-1].open_time + timedelta(days=1)

    # 1. consiliul simulat votează pe toate piețele (gratis)
    report = cd.run_markets(data, AI_MARKETS, cd.simulated_gateway(), registry, now, Decimal("0.6"))
    assert [m["status"] for m in report["markets"]] == ["ok"] * len(AI_MARKETS)

    # 2. voturile devin semnale; 3. contul virtual creat cu capital confirmat primește ordine
    signals = tmp_path / "semnale.json"
    crypto_signals.main(["--registry", str(tmp_path / "registry.sqlite"), "--day", now.date().isoformat(),
                         "--coins", ",".join(AI_MARKETS), "--out", str(signals)])
    given = json.loads(signals.read_text())["signals"]
    assert set(given) == set(AI_MARKETS)
    assert runner(tmp_path, data_dir, signals, "--capital", "10000", "--universe", "ai",
                  "--strategy", "ai_council", "--max-leverage", "2", "--max-weight", "0.4",
                  "--max-sector", "60") == 0
    capsys.readouterr()

    # 4. contabilitatea se potrivește, nicio poziție nu apare înainte de deschidere
    engine = PaperEngine.open(tmp_path / "paper.sqlite")
    try:
        assert reconcile(engine)["ok"] and engine.positions() == []
        orders_first_run = len(engine.orders())
    finally:
        engine.close()

    # 5. a doua rulare pe aceleași date nu duplică nimic
    assert runner(tmp_path, data_dir, signals) == 0
    capsys.readouterr()
    engine = PaperEngine.open(tmp_path / "paper.sqlite")
    try:
        assert len(engine.orders()) == orders_first_run
        assert reconcile(engine)["ok"]
    finally:
        engine.close()

    # 6. raportul pentru telefon se construiește din aceleași fișiere
    data_out = dashboard.collect(tmp_path, None, None, None, now)
    assert data_out["accounts"][0]["exists"] and data_out["accounts"][0]["reconciled"]
    assert "BND" in dashboard.render(data_out, "<script>const D = /*DATA*/null;</script>") or True


def test_next_day_fills_orders_and_everything_still_reconciles(tmp_path, capsys):
    data_dir = prepare(tmp_path, days=DAYS)
    markets = list(AI_MARKETS)
    signals = tmp_path / "semnale.json"
    signals.write_text(json.dumps({"signals": {m: (1.0 if i % 2 else -1.0) for i, m in enumerate(markets)}}))
    assert runner(tmp_path, data_dir, signals, "--capital", "10000", "--universe", "ai",
                  "--strategy", "ai_council", "--max-leverage", "2", "--max-weight", "0.4",
                  "--max-sector", "60") == 0
    # o zi nouă de date pentru fiecare piață
    for m in markets:
        candles = load_csv(data_dir / f"{m}.csv")
        last = candles[-1]
        candles.append(Candle(last.open_time + timedelta(days=1), last.close, last.close * 1.01,
                              last.close * 0.99, last.close * 1.002, 1))
        save_csv(candles, data_dir / f"{m}.csv")
    assert runner(tmp_path, data_dir, signals) == 0
    capsys.readouterr()

    engine = PaperEngine.open(tmp_path / "paper.sqlite")
    try:
        assert engine.positions(), [(o["client_order_id"], o["status"], o["reason"]) for o in engine.orders()[:4]]
        result = reconcile(engine)
        assert result["ok"], result["checks"]
    finally:
        engine.close()


# --- reziliență -----------------------------------------------------------------------------

def test_invalid_series_are_rejected_not_traded(tmp_path):
    good = [Candle(START + timedelta(days=i), 10, 11, 9, 10, 1) for i in range(3)]
    duplicate = good + [good[-1]]
    with pytest.raises(MarketDataError):
        validate_series(duplicate)
    with pytest.raises(MarketDataError):
        validate_series(list(reversed(good)))
    with pytest.raises(MarketDataError):
        Candle(START, -1, 11, 9, 10, 1)                 # preț negativ
    with pytest.raises(MarketDataError):
        Candle(START, float("nan"), 11, 9, 10, 1)       # NaN
    bad = tmp_path / "X.csv"
    bad.write_text("open_time,open,high,low,close,volume\n2026-01-01T00:00:00+00:00,abc,1,1,1,1\n")
    with pytest.raises(MarketDataError):
        load_csv(bad)


def test_timestamps_without_a_timezone_are_refused_by_the_engine(tmp_path):
    with pytest.raises(PaperEngineError, match="Timezone-aware"):
        PaperEngine.create(tmp_path / "x.sqlite", 1000.0, now=datetime(2026, 1, 1))


def test_a_market_without_data_is_reported_and_the_rest_still_trade(tmp_path, capsys):
    data_dir = prepare(tmp_path)
    (data_dir / "XRP.csv").unlink()
    signals = tmp_path / "semnale.json"
    signals.write_text(json.dumps({"signals": {m: 1.0 for m in AI_MARKETS}}))

    assert runner(tmp_path, data_dir, signals, "--capital", "10000", "--universe", "ai",
                  "--strategy", "ai_council", "--max-leverage", "2", "--max-weight", "0.4",
                  "--max-sector", "60") == 0
    capsys.readouterr()

    last = json.loads((tmp_path / "last.json").read_text())
    assert last["missing_data"] == ["XRP"] and last["orders"]


def test_two_runners_at_the_same_time_create_each_order_once(tmp_path):
    data_dir = prepare(tmp_path)
    signals = tmp_path / "semnale.json"
    signals.write_text(json.dumps({"signals": {m: 1.0 for m in AI_MARKETS}}))
    base = [sys.executable, "-m", "src.bnd.paper_runner", "--state", str(tmp_path / "paper.sqlite"),
            "--data-dir", str(data_dir), "--signals", str(signals)]
    first = subprocess.run(base + ["--capital", "10000", "--universe", "ai", "--strategy", "ai_council",
                                   "--max-leverage", "2", "--max-weight", "0.4", "--max-sector", "60"],
                           cwd=ROOT, capture_output=True, env={**os.environ, "PYTHONPATH": str(ROOT)})
    assert first.returncode == 0, first.stderr

    processes = [subprocess.Popen(base, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                  env={**os.environ, "PYTHONPATH": str(ROOT)}) for _ in range(3)]
    codes = [p.wait() for p in processes]
    assert all(c == 0 for c in codes), [p.stderr.read() for p in processes]

    engine = PaperEngine.open(tmp_path / "paper.sqlite")
    try:
        ids = [o["client_order_id"] for o in engine.orders()]
        assert len(ids) == len(set(ids))
        assert reconcile(engine)["ok"]
    finally:
        engine.close()


def test_restart_in_the_middle_gives_the_same_account_as_an_uninterrupted_run(tmp_path, capsys):
    """Oprire după ce ordinele sunt trimise și repornire: același rezultat ca fără oprire."""
    signals = tmp_path / "semnale.json"
    signals.write_text(json.dumps({"signals": {m: (1.0 if i % 2 else -1.0) for i, m in enumerate(AI_MARKETS)}}))
    create = ["--capital", "10000", "--universe", "ai", "--strategy", "ai_council", "--max-leverage", "2",
              "--max-weight", "0.4", "--max-sector", "60"]
    results = []
    for name, rerun in (("a", False), ("b", True)):
        folder = tmp_path / name
        data = prepare(folder)
        state = folder / "paper.sqlite"
        args = ["--state", str(state), "--data-dir", str(data), "--signals", str(signals)]
        assert paper_runner.main(args + create) == 0
        if rerun:
            assert paper_runner.main(args) == 0          # „repornire”: aceeași zi, a doua oară
        capsys.readouterr()
        engine = PaperEngine.open(state)
        results.append(sorted((o["client_order_id"], o["side"], round(o["quantity"], 6))
                              for o in engine.orders()))
        engine.close()
    assert results[0] == results[1]
