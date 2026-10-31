"""Decision registry: record council decisions, settle them, score the agents."""

from datetime import datetime, timedelta, timezone

import pytest

from src.bnd.decision_registry import DecisionRegistry
from src.bnd.decision_rules import decide
from src.bnd.fusion_council import AGENTS, FusionCouncil, Opinion, Vote
from src.bnd.market_data import Candle

T0 = datetime(2026, 1, 5, tzinfo=timezone.utc)
SKILLED, CONTRARIAN = AGENTS[0], AGENTS[1]


def council(up: bool) -> FusionCouncil:
    """SKILLED always calls the move right, CONTRARIAN always wrong, others HOLD."""
    right, wrong = (Vote.BUY, Vote.SELL) if up else (Vote.SELL, Vote.BUY)
    c = FusionCouncil()
    for agent in AGENTS:
        vote = right if agent == SKILLED else wrong if agent == CONTRARIAN else Vote.HOLD
        c.submit(Opinion(agent, vote, f"{agent} reason", 0.8))
    return c


def candles(prices, start=T0):
    return [Candle(start + timedelta(days=i), p, p, p, p, 1) for i, p in enumerate(prices)]


def test_record_is_idempotent_and_settles_after_the_horizon(tmp_path):
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    c = council(up=True)

    assert registry.record("d1", T0, "GOLD", 100.0, c, decide(c), horizon_days=3)
    assert not registry.record("d1", T0, "GOLD", 100.0, c, decide(c), horizon_days=3)
    assert registry.due(T0 + timedelta(days=2)) == []
    assert [d["id"] for d in registry.due(T0 + timedelta(days=3))] == ["d1"]

    data = {"GOLD": candles([100, 101, 102, 110, 120])}
    assert registry.settle_from_candles(data, T0 + timedelta(days=4)) == 1
    assert registry.due(T0 + timedelta(days=10)) == []          # settled once
    perf = registry.performance()
    assert perf["agents"][SKILLED] == {"calls": 1, "hit_rate": 1.0,
                                       "mean_brier": pytest.approx(0.04)}
    assert perf["agents"][CONTRARIAN]["hit_rate"] == 0.0
    assert perf["agents"][AGENTS[2]]["calls"] == 0            # HOLD is not scored


def test_track_record_moves_the_weights(tmp_path):
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    prices = [100.0]
    for i in range(40):
        up = i % 3 != 0
        prices.append(prices[-1] * (1.02 if up else 0.98))
    data = {"SP500": candles(prices)}
    for i in range(40):
        c = council(up=prices[i + 1] > prices[i])
        registry.record(f"d{i}", T0 + timedelta(days=i), "SP500", prices[i], c, decide(c),
                        horizon_days=1)

    registry.settle_from_candles(data, T0 + timedelta(days=60))

    weights = registry.performance()["weights"]
    assert weights[SKILLED] > weights[AGENTS[2]] > weights[CONTRARIAN]
    assert sum(weights.values()) == pytest.approx(1.0)


def test_unsettled_without_data_and_flat_outcomes_are_not_scored(tmp_path):
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    c = council(up=True)
    registry.record("flat", T0, "FX", 1.1, c, decide(c), horizon_days=1)
    registry.record("nodata", T0, "OIL", 70.0, c, decide(c), horizon_days=1)

    settled = registry.settle_from_candles({"FX": candles([1.1, 1.1])}, T0 + timedelta(days=5))

    assert settled == 1
    assert [d["id"] for d in registry.due(T0 + timedelta(days=5))] == ["nodata"]
    assert registry.performance()["agents"][SKILLED]["calls"] == 0


def test_validation(tmp_path):
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    c = council(up=True)
    with pytest.raises(ValueError):
        registry.record("x", T0, "GOLD", 0, c, decide(c))
    with pytest.raises(ValueError):
        registry.record("x", datetime(2026, 1, 1), "GOLD", 1, c, decide(c))


def _majority_of(up):
    """O decizie de consiliu pentru test: BUY dacă urcă, altfel SELL."""
    from src.bnd.decision_rules import CouncilDecision, DecisionRule

    vote = Vote.BUY if up else Vote.SELL
    return CouncilDecision(vote, DecisionRule.MAJORITY, {}, (), (), False, ())


def test_comparison_counts_council_bot_and_always_long(tmp_path):
    registry = DecisionRegistry(tmp_path / "r.sqlite")
    # (rezultat după orizont, semnalul botului): consiliul are de fiecare dată dreptate.
    cases = [(+0.05, +1), (-0.04, -1), (+0.02, -1), (-0.03, 0)]
    prices = [100.0]
    for outcome, _ in cases:
        prices.append(prices[-1] * (1 + outcome))
    for i, (outcome, bot) in enumerate(cases):
        registry.record(f"d{i}", T0 + timedelta(days=2 * i), "X", prices[i], council(outcome > 0),
                        _majority_of(outcome > 0), horizon_days=1, meta={"bot_signal": bot})

    registry.settle_from_candles(
        {"X": [Candle(T0 + timedelta(days=2 * i + 1), p, p, p, p, 1)
               for i, p in enumerate(prices[1:])]},
        T0 + timedelta(days=30))
    comparison = registry.comparison()

    assert comparison["settled_decisions"] == 4
    assert comparison["always_long"]["calls"] == 4
    assert comparison["always_long"]["hit_rate"] == 0.5          # 2 urcări din 4
    assert comparison["bot"]["calls"] == 3                        # semnalul 0 nu e un apel
    assert comparison["bot"]["hit_rate"] == pytest.approx(2 / 3)
    assert comparison["council"]["calls"] == 4 and comparison["council"]["hit_rate"] == 1.0
    assert comparison["council"]["mean_return_pct"] == pytest.approx(3.5, abs=0.01)


def test_has_and_old_registries_get_the_meta_column(tmp_path):
    import sqlite3

    path = tmp_path / "old.sqlite"
    db = sqlite3.connect(path)
    db.executescript("""CREATE TABLE decisions (id TEXT PRIMARY KEY, time TEXT NOT NULL,
        symbol TEXT NOT NULL, price REAL NOT NULL, horizon_days INTEGER NOT NULL,
        vote TEXT NOT NULL, rule TEXT NOT NULL, uncertain INTEGER NOT NULL,
        settled_at TEXT, outcome_price REAL, outcome_return REAL);""")
    db.commit()
    db.close()

    registry = DecisionRegistry(path)
    c = council(up=True)

    assert not registry.has("a")
    assert registry.record("a", T0, "X", 1.0, c, decide(c), meta={"bot_signal": 1})
    assert registry.has("a")


def test_lean_ignores_hold_and_is_read_from_the_saved_votes(tmp_path):
    from src.bnd.fusion_council import AGENTS, FusionCouncil, Opinion

    def split(buys, sells):
        c = FusionCouncil()
        for i, agent in enumerate(AGENTS):
            vote = Vote.BUY if i < buys else Vote.SELL if i < buys + sells else Vote.HOLD
            c.submit(Opinion(agent, vote, "motiv", 0.7))
        return c

    registry = DecisionRegistry(tmp_path / "r.sqlite")
    # 1 BUY + 4 HOLD (fără majoritate, dar înclină spre cumpărare, iar prețul urcă);
    # 2 SELL + 3 HOLD (înclină spre vânzare, prețul urcă: greșit); 5 HOLD (fără înclinație).
    for i, (buys, sells, outcome) in enumerate([(1, 0, +0.05), (0, 2, +0.03), (0, 0, +0.02)]):
        c = split(buys, sells)
        registry.record(f"d{i}", T0 + timedelta(days=2 * i), "X", 100.0, c, decide(c),
                        horizon_days=1)
    registry.settle_from_candles(
        {"X": [Candle(T0 + timedelta(days=2 * i + 1), 100 * (1 + o), 100 * (1 + o), 100 * (1 + o),
                      100 * (1 + o), 1) for i, o in enumerate([0.05, 0.03, 0.02])]},
        T0 + timedelta(days=30))

    comparison = registry.comparison()

    assert comparison["council"]["calls"] == 0                 # nicio majoritate clară
    assert comparison["lean"]["calls"] == 2                    # a treia nu înclină nicăieri
    assert comparison["lean"]["hit_rate"] == 0.5
