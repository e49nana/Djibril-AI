"""
Djibril AI — Signal Publisher

Writes TradeSignal as timestamped JSON to the MQL5 signals/ directory,
maintains a SQLite history of the last 1000 signals, and publishes
to an asyncio queue for WebSocket broadcast.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from ..utils.config import get_settings
    from ..utils.logger import get_logger, timed
    from ..utils.models import TradeSignal, WSMessage, WSMessageType
except ImportError:
    from utils.config import get_settings
    from utils.logger import get_logger, timed
    from utils.models import TradeSignal, WSMessage, WSMessageType

logger = get_logger(__name__)


class SignalPublisher:
    """Publishes trade signals to file, database, and WebSocket queue."""

    def __init__(
        self,
        db_path: str = "djibril.db",
        ws_queue: Optional[asyncio.Queue[WSMessage]] = None,
    ) -> None:
        self._settings = get_settings()
        self._db_path = db_path
        self._ws_queue = ws_queue
        self._output_dir = self._settings.signal.output_path
        self._init_db()

    def _init_db(self) -> None:
        """Create the signal_history table."""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signal_history (
                    signal_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    confidence REAL DEFAULT 0.0,
                    entry_price REAL DEFAULT 0.0,
                    stop_loss REAL DEFAULT 0.0,
                    take_profit REAL DEFAULT 0.0,
                    lot_size REAL DEFAULT 0.0,
                    geo_score INTEGER DEFAULT 0,
                    urgency TEXT DEFAULT 'low',
                    reasoning TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    signal_json TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signal_created
                ON signal_history (created_at DESC)
            """)
            conn.commit()
        finally:
            conn.close()

    @timed
    async def publish(self, signal: TradeSignal) -> None:
        """Publish a trade signal to all outputs.

        Args:
            signal: The TradeSignal to publish.
        """
        signal_json = signal.model_dump_json(indent=2)
        signal_dict = json.loads(signal_json)

        # 1. Write JSON file for MQL5 EA
        self._write_signal_file(signal, signal_json)

        # 2. Store in SQLite history
        self._store_in_history(signal, signal_json)

        # 3. Publish to WebSocket queue
        if self._ws_queue is not None:
            msg = WSMessage(
                type=WSMessageType.SIGNAL,
                payload=signal_dict,
            )
            try:
                self._ws_queue.put_nowait(msg)
                logger.debug("signal_queued_ws", signal_id=signal.signal_id)
            except asyncio.QueueFull:
                logger.warning("ws_queue_full")

        logger.info(
            "signal_published",
            signal_id=signal.signal_id,
            action=signal.action.value,
        )

    def _write_signal_file(self, signal: TradeSignal, signal_json: str) -> None:
        """Write signal as a JSON file to the MQL5 signals directory.

        Creates two files:
        - latest_signal.json (always overwritten — EA reads this)
        - signal_{id}.json (timestamped archive)

        Args:
            signal: The signal.
            signal_json: Pre-serialized JSON string.
        """
        try:
            # Latest signal (overwrite)
            latest_path = self._output_dir / "latest_signal.json"
            latest_path.write_text(signal_json, encoding="utf-8")

            # Archived signal
            archive_path = self._output_dir / f"signal_{signal.signal_id}.json"
            archive_path.write_text(signal_json, encoding="utf-8")

            logger.debug("signal_file_written", path=str(latest_path))

            # Cleanup old archive files (keep last 100)
            self._cleanup_archive_files()

        except OSError as exc:
            logger.error("signal_file_write_error", error=str(exc))

    def _cleanup_archive_files(self, keep: int = 100) -> None:
        """Remove old archive signal files.

        Args:
            keep: Number of most recent files to retain.
        """
        try:
            files = sorted(
                self._output_dir.glob("signal_OG-*.json"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            for old_file in files[keep:]:
                old_file.unlink()
        except OSError:
            pass

    def _store_in_history(self, signal: TradeSignal, signal_json: str) -> None:
        """Insert signal into SQLite history, maintaining max 1000 records.

        Args:
            signal: The signal.
            signal_json: Serialized JSON.
        """
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO signal_history
                (signal_id, action, symbol, confidence, entry_price, stop_loss,
                 take_profit, lot_size, geo_score, urgency, reasoning,
                 created_at, signal_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.signal_id,
                    signal.action.value,
                    signal.symbol,
                    signal.confidence,
                    signal.entry_price,
                    signal.stop_loss,
                    signal.take_profit,
                    signal.lot_size,
                    signal.geo_score,
                    signal.urgency.value,
                    signal.reasoning[:500],
                    signal.created_at.isoformat(),
                    signal_json,
                ),
            )

            # Trim to max history
            max_records = self._settings.signal.history_max_records
            conn.execute(
                """
                DELETE FROM signal_history
                WHERE signal_id NOT IN (
                    SELECT signal_id FROM signal_history
                    ORDER BY created_at DESC
                    LIMIT ?
                )
                """,
                (max_records,),
            )
            conn.commit()
        except sqlite3.Error as exc:
            logger.error("signal_history_db_error", error=str(exc))
        finally:
            conn.close()

    def get_history(self, limit: int = 50) -> list[dict]:
        """Retrieve recent signal history.

        Args:
            limit: Max records to return.

        Returns:
            List of signal dicts, newest first.
        """
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute(
                """
                SELECT signal_json FROM signal_history
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [json.loads(row[0]) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_latest(self) -> Optional[dict]:
        """Retrieve the most recent signal.

        Returns:
            Signal dict or None.
        """
        history = self.get_history(limit=1)
        return history[0] if history else None
