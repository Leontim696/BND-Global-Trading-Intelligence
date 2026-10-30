"""Response cache for AI calls: the same question is never paid for twice.

The key is a SHA-256 of agent, model, market, symbol and the exact context
sent, so any change in the data or the prompt is a new question. Entries
expire after ``ttl`` (default 12 hours): markets move, and an old answer
must not pose as a fresh one. Hits and the money they saved are counted.
"""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from .ai_gateway import AIResponse
from .fusion_council import Vote

SCHEMA = """
CREATE TABLE IF NOT EXISTS responses (
    key TEXT PRIMARY KEY, response TEXT NOT NULL, cost_usd TEXT NOT NULL,
    stored_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stats (
    id INTEGER PRIMARY KEY CHECK (id = 1), hits INTEGER NOT NULL,
    misses INTEGER NOT NULL, saved_usd TEXT NOT NULL
);
INSERT OR IGNORE INTO stats (id, hits, misses, saved_usd) VALUES (1, 0, 0, '0');
"""


def cache_key(agent: str, model: str, market: str, symbol: str, context: str) -> str:
    payload = json.dumps([agent, model, market, symbol, context], ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


class ResponseCache:
    def __init__(self, path, ttl: timedelta = timedelta(hours=12), clock=None):
        if ttl <= timedelta(0):
            raise ValueError("ttl must be positive")
        self.path, self.ttl = str(Path(path)), ttl
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.executescript(SCHEMA)
        finally:
            db.close()

    @contextmanager
    def _connect(self):
        """One write-locked transaction, so concurrent counters never lose updates."""
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

    def get(self, key: str) -> AIResponse | None:
        """A fresh stored answer, or None (counted as a miss)."""
        with self._connect() as db:
            row = db.execute("SELECT response, cost_usd, stored_at FROM responses WHERE key = ?",
                             (key,)).fetchone()
            fresh = row is not None and \
                self.clock() - datetime.fromisoformat(row[2]) <= self.ttl
            if not fresh:
                db.execute("UPDATE stats SET misses = misses + 1")
                return None
            saved = Decimal(db.execute("SELECT saved_usd FROM stats").fetchone()[0])
            db.execute("UPDATE stats SET hits = hits + 1, saved_usd = ?",
                       (str(saved + Decimal(row[1])),))
        data = json.loads(row[0])
        data["vote"] = Vote(data["vote"])
        return AIResponse(**data)

    def put(self, key: str, response: AIResponse, cost_usd: Decimal) -> None:
        data = {**vars(response), "vote": response.vote.value}
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO responses (key, response, cost_usd, stored_at)"
                       " VALUES (?, ?, ?, ?)",
                       (key, json.dumps(data), str(cost_usd), self.clock().isoformat()))

    def stats(self) -> dict:
        with self._connect() as db:
            hits, misses, saved = db.execute("SELECT hits, misses, saved_usd FROM stats").fetchone()
            entries = db.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
        return {"hits": hits, "misses": misses, "saved_usd": saved, "entries": entries}
