"""End-to-end paper runs: restarts, repeated runs and concurrent writers."""

import threading
from datetime import timedelta

from src.bnd.paper_engine import OrderRequest, PaperEngine
from src.bnd.paper_runner import instrument_for, run_daily
from tests.test_paper_runner import (
    DAY,
    MARKETS,
    START,
    config,
    factory,
    make_data,
    now_after,
)


def state(engine):
    """Everything that defines the account, without wall-clock journal times."""
    return {
        "summary": engine.summary(),
        "orders": [{k: v for k, v in o.items()} for o in engine.orders()],
        "fills": engine.fills(),
        "marks": {m.name: engine.mark(m.name) for m in MARKETS},
    }


def daily_windows(data, first=100):
    for end in range(first, len(next(iter(data.values()))) + 1):
        yield {name: candles[:end] for name, candles in data.items()}


def test_restart_every_day_matches_one_long_session(tmp_path):
    data = make_data(160)

    kept = PaperEngine.create(tmp_path / "kept.sqlite", 10_000, currency="USD", now=START)
    for window in daily_windows(data):
        run_daily(kept, window, MARKETS, factory, config(), "sma", now_after(window))

    PaperEngine.create(tmp_path / "restarted.sqlite", 10_000, currency="USD", now=START).close()
    for window in daily_windows(data):
        engine = PaperEngine.open(tmp_path / "restarted.sqlite")
        run_daily(engine, window, MARKETS, factory, config(), "sma", now_after(window))
        engine.close()

    reopened = PaperEngine.open(tmp_path / "restarted.sqlite")
    assert state(reopened) == state(kept)
    assert kept.fills()                       # the scenario actually traded


def test_running_each_day_twice_changes_nothing(tmp_path):
    data = make_data(160)
    once = PaperEngine.create(tmp_path / "once.sqlite", 10_000, currency="USD", now=START)
    twice = PaperEngine.create(tmp_path / "twice.sqlite", 10_000, currency="USD", now=START)

    for window in daily_windows(data):
        run_daily(once, window, MARKETS, factory, config(), "sma", now_after(window))
        for _ in range(2):
            run_daily(twice, window, MARKETS, factory, config(), "sma", now_after(window))

    assert state(twice) == state(once)


def test_missed_days_are_caught_up_in_order(tmp_path):
    data = make_data(160)
    engine = PaperEngine.create(tmp_path / "gap.sqlite", 10_000, currency="USD", now=START)
    windows = list(daily_windows(data))
    run_daily(engine, windows[0], MARKETS, factory, config(), "sma", now_after(windows[0]))

    # Three days without a run: all candles are processed on the next one.
    report = run_daily(engine, windows[3], MARKETS, factory, config(), "sma",
                       now_after(windows[3]))

    assert report["candles_processed"] == 3 * len(MARKETS)
    times = [f["time"] for f in engine.fills()]
    assert times == sorted(times)


def test_concurrent_submissions_of_one_order_id_create_one_order(tmp_path):
    data = make_data(30)
    path = tmp_path / "shared.sqlite"
    setup = PaperEngine.create(path, 10_000, currency="USD", now=START)
    setup.register_instrument(instrument_for(MARKETS[0]))
    setup.on_bar("UP", data["UP"][-1])
    setup.close()
    now = data["UP"][-1].open_time + timedelta(hours=1)
    barrier = threading.Barrier(4)
    results, errors = [], []

    def submit():
        engine = PaperEngine.open(path)
        try:
            barrier.wait()
            results.append(engine.submit_order(
                OrderRequest("same-id", "UP", "BUY", 10,
                                       stop_loss=data["UP"][-1].close * 0.99), now)["status"])
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)
        finally:
            engine.close()

    threads = [threading.Thread(target=submit) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    engine = PaperEngine.open(path)
    assert errors == []
    assert len(engine.orders()) == 1 and results.count("PENDING") == 4
    assert len(engine.journal("duplicate_order_ignored")) == 3


def test_concurrent_bars_for_one_market_are_processed_once(tmp_path):
    data = make_data(30)
    path = tmp_path / "bars.sqlite"
    setup = PaperEngine.create(path, 10_000, currency="USD", now=START)
    setup.register_instrument(instrument_for(MARKETS[0]))
    setup.on_bar("UP", data["UP"][-2])
    setup.submit_order(OrderRequest("buy", "UP", "BUY", 10,
                                    stop_loss=data["UP"][-2].close * 0.9),
                       data["UP"][-2].open_time + DAY / 2)
    setup.close()
    barrier = threading.Barrier(3)

    def feed():
        engine = PaperEngine.open(path)
        barrier.wait()
        engine.on_bar("UP", data["UP"][-1])
        engine.close()

    threads = [threading.Thread(target=feed) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    engine = PaperEngine.open(path)
    assert len(engine.fills()) == 1
    assert len(engine.journal("bar_ignored")) == 2
