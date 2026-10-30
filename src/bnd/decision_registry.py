"""Decision registry: every council decision, then what the market did.

Each decision stores every agent's own vote and confidence (initial and
final), the council's decision, the price and a horizon. Once the horizon
has passed, the decision is settled with the first close at or after it.
Settled decisions feed ``AgentScorebook`` (Brier score of each agent's
calls), so the weighted decision rule learns from real paper outcomes
instead of fixed weights. Read-only analysis; nothing here trades.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .decision_rules import AgentScorebook, CouncilDecision
from .fusion_council import AGENTS, FusionCouncil, Vote

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY, time TEXT NOT NULL, symbol TEXT NOT NULL,
    price REAL NOT NULL, horizon_days INTEGER NOT NULL, vote TEXT NOT NULL,
    rule TEXT NOT NULL, uncertain INTEGER NOT NULL,
    settled_at TEXT, outcome_price REAL, outcome_return REAL
);
CREATE TABLE IF NOT EXISTS votes (
    decision_id TEXT NOT NULL, agent TEXT NOT NULL, stage TEXT NOT NULL,
    vote TEXT NOT NULL, confidence REAL NOT NULL,
    PRIMARY KEY (decision_id, agent, stage)
);
"""


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Timezone-aware times required")
    return value.astimezone(timezone.utc).isoformat()


class DecisionRegistry:
    def __init__(self, path):
        self.path = str(Path(path))
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.executescript(SCHEMA)
        finally:
            db.close()

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except BaseException:
                db.execute("ROLLBACK")
                raise
            db.execute("COMMIT")
        finally:
            db.close()

    def record(self, decision_id: str, time: datetime, symbol: str, price: float,
               council: FusionCouncil, decision: CouncilDecision, horizon_days: int = 5) -> bool:
        """Store a decision once; False if this id was already recorded."""
        if price <= 0 or horizon_days < 1:
            raise ValueError("price must be positive and horizon_days >= 1")
        with self._db() as db:
            if db.execute("SELECT 1 FROM decisions WHERE id = ?", (decision_id,)).fetchone():
                return False
            db.execute("INSERT INTO decisions (id, time, symbol, price, horizon_days, vote, rule,"
                       " uncertain) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (decision_id, _iso(time), symbol, price, horizon_days,
                        decision.vote.value, decision.rule.value, int(decision.uncertain)))
            for stage, opinions in (("initial", council.initial_opinions),
                                    ("final", council.current_opinions())):
                for agent, opinion in opinions.items():
                    db.execute("INSERT INTO votes VALUES (?, ?, ?, ?, ?)",
                               (decision_id, agent, stage, opinion.vote.value, opinion.confidence))
        return True

    def due(self, now: datetime) -> list[dict]:
        """Unsettled decisions whose horizon has passed."""
        with self._db() as db:
            rows = db.execute("SELECT id, time, symbol, price, horizon_days FROM decisions"
                              " WHERE settled_at IS NULL ORDER BY time").fetchall()
        return [{"id": r[0], "time": r[1], "symbol": r[2], "price": r[3], "horizon_days": r[4]}
                for r in rows
                if datetime.fromisoformat(r[1]) + timedelta(days=r[4]) <= now]

    def settle_from_candles(self, candles_by_symbol: dict, now: datetime) -> int:
        """Settle every due decision with the first close at or after its horizon."""
        settled = 0
        for row in self.due(now):
            target = datetime.fromisoformat(row["time"]) + timedelta(days=row["horizon_days"])
            candles = candles_by_symbol.get(row["symbol"], ())
            later = [c for c in candles if c.open_time >= target]
            if not later:
                continue
            price = later[0].close
            with self._db() as db:
                db.execute("UPDATE decisions SET settled_at = ?, outcome_price = ?,"
                           " outcome_return = ? WHERE id = ? AND settled_at IS NULL",
                           (_iso(now), price, price / row["price"] - 1, row["id"]))
            settled += 1
        return settled

    def _settled_votes(self, stage: str):
        with self._db() as db:
            return db.execute(
                "SELECT v.agent, v.vote, v.confidence, d.outcome_return FROM votes v"
                " JOIN decisions d ON d.id = v.decision_id"
                " WHERE d.settled_at IS NOT NULL AND v.stage = ? AND d.outcome_return != 0"
                " ORDER BY d.time", (stage,)).fetchall()

    def scorebook(self, stage: str = "initial", **options) -> AgentScorebook:
        """AgentScorebook from settled outcomes (initial, independent votes by default)."""
        book = AgentScorebook(**options)
        for agent, vote, confidence, outcome in self._settled_votes(stage):
            book.record(agent, Vote(vote), confidence, outcome > 0)
        return book

    def performance(self, stage: str = "initial") -> dict:
        """Per agent: scored calls, hit rate, mean Brier; plus the council itself."""
        stats = {agent: {"calls": 0, "hits": 0, "brier": 0.0} for agent in AGENTS}
        for agent, vote, confidence, outcome in self._settled_votes(stage):
            if vote == Vote.HOLD.value:
                continue
            hit = (vote == Vote.BUY.value) == (outcome > 0)
            entry = stats[agent]
            entry["calls"] += 1
            entry["hits"] += hit
            entry["brier"] += (confidence - (1.0 if hit else 0.0)) ** 2
        agents = {
            agent: {"calls": s["calls"],
                    "hit_rate": s["hits"] / s["calls"] if s["calls"] else None,
                    "mean_brier": s["brier"] / s["calls"] if s["calls"] else None}
            for agent, s in stats.items()
        }
        with self._db() as db:
            rows = db.execute("SELECT vote, outcome_return FROM decisions WHERE settled_at"
                              " IS NOT NULL AND vote != 'HOLD' AND outcome_return != 0"
                              " AND uncertain = 0").fetchall()
        hits = sum((vote == Vote.BUY.value) == (outcome > 0) for vote, outcome in rows)
        return {"agents": agents, "weights": self.scorebook(stage).weights(),
                "council": {"calls": len(rows), "hit_rate": hits / len(rows) if rows else None}}
