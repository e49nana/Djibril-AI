"""
Djibril AI — Agent Memory

Persistent SQLite memory for the DJIBRIL agent.
Stores geopolitical events, signals issued, price outcomes,
and conversation history for long-term learning.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite

try:
    from ..utils.logger import get_logger
    from ..utils.models import NewsItem, TradeSignal
except ImportError:
    from utils.logger import get_logger
    from utils.models import NewsItem, TradeSignal

logger = get_logger(__name__)

_DEFAULT_DB = os.environ.get("AGENT_DB_PATH", "./djibril_memory.db")


class AgentMemory:
    """Persistent SQLite memory backing the DJIBRIL agent.

    Stores geo events, trade signals with outcomes, chat history,
    and price snapshots for retrospective learning.
    """

    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        self._db_path = db_path
        self._initialized = False

    async def initialize(self) -> None:
        """Create all tables if they don't exist. Safe to call multiple times."""
        if self._initialized:
            return
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()
        self._initialized = True
        logger.info("agent_memory_initialized", db=self._db_path)

    # ── events ──────────────────────────────────────

    async def record_event(
        self, item: NewsItem, geo_score: int, urgency: str
    ) -> int:
        """Insert a geopolitical event.

        Args:
            item: The news item.
            geo_score: Geo score at time of event.
            urgency: Urgency level string.

        Returns:
            Row id of the inserted event.
        """
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """INSERT INTO geo_events
                   (title, category, score, urgency, keywords, source, event_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.title,
                    item.category.value,
                    geo_score,
                    urgency,
                    json.dumps(item.keywords_matched),
                    item.source_name,
                    item.published_at.isoformat(),
                ),
            )
            await db.commit()
            row_id = cursor.lastrowid or 0
            logger.info("memory_event_recorded", title=item.title[:60], id=row_id)
            return row_id

    async def update_price_impact(self, event_id: int, price_change_pct: float) -> None:
        """Set the observed price impact for a past event.

        Args:
            event_id: Row id of the geo_event.
            price_change_pct: Percentage price change in 4h after event.
        """
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE geo_events SET impact_on_price = ? WHERE id = ?",
                (price_change_pct, event_id),
            )
            await db.commit()

    async def get_recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the N most recent geo events.

        Args:
            limit: Max rows.

        Returns:
            List of event dicts, newest first.
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM geo_events ORDER BY recorded_at DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def search_similar_events(
        self, keywords: list[str], limit: int = 5
    ) -> list[dict[str, Any]]:
        """Find past events matching any of the given keywords.

        Args:
            keywords: Keywords to match against stored keywords JSON.
            limit: Max results.

        Returns:
            Matching events with their historical price impact.
        """
        if not keywords:
            return []
        conditions = " OR ".join(["keywords LIKE ?" for _ in keywords])
        params = [f"%{kw}%" for kw in keywords]
        params.append(str(limit))
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM geo_events WHERE {conditions} "
                "ORDER BY recorded_at DESC LIMIT ?",
                params,
            )
            return [dict(row) for row in await cursor.fetchall()]

    # ── signals ─────────────────────────────────────

    async def record_signal(self, signal: TradeSignal) -> None:
        """Insert a trade signal into history.

        Args:
            signal: The TradeSignal to record.
        """
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO signals_history
                   (signal_id, action, confidence, entry_price, stop_loss,
                    take_profit, geo_score, reasoning, signal_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    signal.signal_id,
                    signal.action.value,
                    signal.confidence,
                    signal.entry_price,
                    signal.stop_loss,
                    signal.take_profit,
                    signal.geo_score,
                    signal.reasoning[:500],
                    signal.created_at.isoformat(),
                ),
            )
            await db.commit()
            logger.info("memory_signal_recorded", signal_id=signal.signal_id)

    async def resolve_signal(
        self, signal_id: str, outcome: str, pnl_pct: float
    ) -> None:
        """Update a signal with its actual outcome.

        Args:
            signal_id: The signal identifier.
            outcome: "win", "loss", or "flat".
            pnl_pct: Percentage profit/loss.
        """
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """UPDATE signals_history
                   SET outcome = ?, pnl_pct = ?, resolved_at = ?
                   WHERE signal_id = ?""",
                (outcome, pnl_pct, datetime.now(timezone.utc).isoformat(), signal_id),
            )
            await db.commit()

    async def get_recent_signals(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return the N most recent signals.

        Args:
            limit: Max rows.

        Returns:
            List of signal dicts, newest first.
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM signals_history ORDER BY signal_at DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def get_signal_performance(self) -> dict[str, Any]:
        """Compute aggregate performance stats from resolved signals.

        Returns:
            Dict with total, wins, losses, win_rate, avg_pnl, best, worst.
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                "SELECT * FROM signals_history WHERE outcome IS NOT NULL"
            )
            rows = [dict(r) for r in await cursor.fetchall()]

        if not rows:
            return {
                "total": 0, "wins": 0, "losses": 0,
                "win_rate": 0.0, "avg_pnl": 0.0,
                "best_signal": None, "worst_signal": None,
            }

        wins = [r for r in rows if r["outcome"] == "win"]
        losses = [r for r in rows if r["outcome"] == "loss"]
        pnls = [r["pnl_pct"] for r in rows if r["pnl_pct"] is not None]

        best = max(rows, key=lambda r: r.get("pnl_pct") or -9999)
        worst = min(rows, key=lambda r: r.get("pnl_pct") or 9999)

        return {
            "total": len(rows),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(rows) if rows else 0.0,
            "avg_pnl": sum(pnls) / len(pnls) if pnls else 0.0,
            "best_signal": best.get("signal_id"),
            "worst_signal": worst.get("signal_id"),
        }

    # ── conversations ───────────────────────────────

    async def add_message(
        self, role: str, content: str, context_signal_id: Optional[str] = None
    ) -> None:
        """Append a message to the conversation log.

        Args:
            role: "user" or "assistant".
            content: Message text.
            context_signal_id: Optional signal this message refers to.
        """
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO conversations (role, content, context_signal_id)
                   VALUES (?, ?, ?)""",
                (role, content, context_signal_id),
            )
            await db.commit()

    async def get_conversation_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the N most recent conversation messages.

        Args:
            limit: Max messages.

        Returns:
            List of {role, content, created_at} dicts, oldest first.
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT role, content, created_at FROM conversations
                   ORDER BY id DESC LIMIT ?""",
                (limit,),
            )
            rows = [dict(r) for r in await cursor.fetchall()]
        rows.reverse()  # oldest first for conversation flow
        return rows

    # ── price snapshots ─────────────────────────────

    async def record_price_snapshot(self, symbol: str, price: float) -> None:
        """Insert a price observation.

        Args:
            symbol: e.g. "WTI".
            price: Current price.
        """
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO price_snapshots (symbol, price) VALUES (?, ?)",
                (symbol, price),
            )
            await db.commit()


# ── Schema ──────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS geo_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT,
    score INTEGER,
    urgency TEXT,
    keywords TEXT,
    source TEXT,
    impact_on_price REAL,
    event_at TIMESTAMP,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS signals_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT UNIQUE,
    action TEXT,
    confidence REAL,
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    geo_score INTEGER,
    reasoning TEXT,
    outcome TEXT,
    pnl_pct REAL,
    signal_at TIMESTAMP,
    resolved_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT,
    content TEXT,
    context_signal_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT DEFAULT 'WTI',
    price REAL,
    snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# ── Singleton ───────────────────────────────────────

_memory_instance: Optional[AgentMemory] = None


def get_memory() -> AgentMemory:
    """Return the global AgentMemory singleton."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = AgentMemory()
    return _memory_instance
