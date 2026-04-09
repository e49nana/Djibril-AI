"""
Djibril AI — RSS Aggregator

Collects geopolitical news from multiple RSS feeds asynchronously.
Deduplicates by title hash, filters by Iran/oil keywords, stores in SQLite.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import aiohttp
import feedparser

try:
    from ..utils.config import get_settings
    from ..utils.logger import get_logger, timed
    from ..utils.models import NewsCategory, NewsItem, SignalSource
except ImportError:
    from utils.config import get_settings
    from utils.logger import get_logger, timed
    from utils.models import NewsCategory, NewsItem, SignalSource

logger = get_logger(__name__)

# ── Category detection patterns ──
_CATEGORY_PATTERNS: dict[NewsCategory, list[str]] = {
    NewsCategory.MILITARY: [
        r"\bmilitary\b", r"\bstrike\b", r"\bmissile\b", r"\bdrone\b",
        r"\bwarship\b", r"\bnavy\b", r"\bairforce\b", r"\battack\b",
        r"\bweapon\b", r"\barms\b", r"\btroops?\b",
    ],
    NewsCategory.SANCTIONS: [
        r"\bsanction", r"\bembargo\b", r"\bfreeze\b.*asset",
        r"\bblacklist\b", r"\brestriction\b",
    ],
    NewsCategory.DIPLOMATIC: [
        r"\bdiplomat", r"\bnegotiat", r"\btreaty\b", r"\bagreement\b",
        r"\bsummit\b", r"\bambassador\b", r"\bjcpoa\b", r"\bnuclear deal\b",
    ],
    NewsCategory.INFRASTRUCTURE: [
        r"\bpipeline\b", r"\brefinery\b", r"\bport\b", r"\btanker\b",
        r"\binfrastructure\b", r"\bfacility\b",
    ],
    NewsCategory.ENERGY: [
        r"\bopec\b", r"\boil\b", r"\bcrude\b", r"\bbrent\b", r"\bwti\b",
        r"\bbarrel\b", r"\bnatural gas\b", r"\benergy\b", r"\bpetroleum\b",
    ],
    NewsCategory.CONFLICT: [
        r"\bconflict\b", r"\bwar\b", r"\bescalat", r"\btension\b",
        r"\bclash\b", r"\bhostil", r"\bblockade\b",
    ],
}


class RSSAggregator:
    """Async RSS feed collector with deduplication and keyword filtering."""

    def __init__(self, db_path: str = "djibril.db") -> None:
        self._settings = get_settings()
        self._db_path = db_path
        self._seen_hashes: set[str] = set()
        self._init_db()

    def _init_db(self) -> None:
        """Create the news_items table if it doesn't exist."""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS news_items (
                    title_hash TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    url TEXT DEFAULT '',
                    source_name TEXT DEFAULT '',
                    source_type TEXT DEFAULT 'rss',
                    category TEXT DEFAULT 'other',
                    published_at TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    keywords_matched TEXT DEFAULT '[]',
                    relevance_score REAL DEFAULT 0.0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_news_published
                ON news_items (published_at DESC)
            """)
            conn.commit()
            # Load existing hashes for dedup
            cursor = conn.execute("SELECT title_hash FROM news_items")
            self._seen_hashes = {row[0] for row in cursor.fetchall()}
            logger.info("rss_db_initialized", existing_items=len(self._seen_hashes))
        finally:
            conn.close()

    @timed
    async def fetch_all_feeds(self) -> List[NewsItem]:
        """Fetch all configured RSS feeds concurrently.

        Returns:
            List of new, deduplicated, keyword-filtered NewsItem objects.
        """
        feeds = self._settings.RSS_FEEDS
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [
                self._fetch_single_feed(session, name, url)
                for name, url in feeds.items()
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        all_items: List[NewsItem] = []
        for i, result in enumerate(results):
            feed_name = list(feeds.keys())[i]
            if isinstance(result, Exception):
                logger.warning(
                    "rss_feed_failed",
                    feed=feed_name,
                    error=str(result),
                )
                continue
            all_items.extend(result)

        # Deduplicate and filter
        new_items = self._deduplicate(all_items)
        filtered = self._filter_by_keywords(new_items)

        # Store in SQLite
        if filtered:
            self._store_items(filtered)

        logger.info(
            "rss_fetch_complete",
            total_raw=len(all_items),
            new_unique=len(new_items),
            keyword_matched=len(filtered),
        )
        return filtered

    async def _fetch_single_feed(
        self,
        session: aiohttp.ClientSession,
        feed_name: str,
        feed_url: str,
    ) -> List[NewsItem]:
        """Fetch and parse a single RSS feed.

        Args:
            session: Active aiohttp session.
            feed_name: Human-readable feed identifier.
            feed_url: RSS feed URL.

        Returns:
            List of parsed NewsItem objects from this feed.
        """
        try:
            async with session.get(feed_url) as resp:
                if resp.status != 200:
                    logger.warning(
                        "rss_http_error",
                        feed=feed_name,
                        status=resp.status,
                    )
                    return []
                raw = await resp.text()
        except Exception as exc:
            logger.warning("rss_fetch_error", feed=feed_name, error=str(exc))
            return []

        parsed = feedparser.parse(raw)
        items: List[NewsItem] = []

        for entry in parsed.entries:
            title = entry.get("title", "").strip()
            if not title:
                continue

            description = entry.get("summary", entry.get("description", "")).strip()
            url = entry.get("link", "")
            published = entry.get("published_parsed") or entry.get("updated_parsed")

            if published:
                try:
                    pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    pub_dt = datetime.now(timezone.utc)
            else:
                pub_dt = datetime.now(timezone.utc)

            items.append(
                NewsItem(
                    title=title,
                    description=description[:500],
                    url=url,
                    source_name=feed_name,
                    source_type=SignalSource.RSS,
                    published_at=pub_dt,
                    fetched_at=datetime.now(timezone.utc),
                )
            )

        logger.debug("rss_feed_parsed", feed=feed_name, entries=len(items))
        return items

    def _deduplicate(self, items: List[NewsItem]) -> List[NewsItem]:
        """Remove items already seen (by title hash).

        Args:
            items: Raw list of NewsItem objects.

        Returns:
            Only items not previously seen.
        """
        new_items: List[NewsItem] = []
        for item in items:
            h = item.title_hash
            if h not in self._seen_hashes:
                self._seen_hashes.add(h)
                new_items.append(item)
        return new_items

    def _filter_by_keywords(self, items: List[NewsItem]) -> List[NewsItem]:
        """Keep only items matching geopolitical keywords.

        Args:
            items: Deduplicated NewsItem list.

        Returns:
            Items containing at least one geo keyword, with matched keywords
            and category annotated.
        """
        keywords = self._settings.GEO_KEYWORDS
        filtered: List[NewsItem] = []

        for item in items:
            text = f"{item.title} {item.description}".lower()
            matched = [kw for kw in keywords if kw in text]
            if matched:
                item.keywords_matched = matched
                item.relevance_score = min(len(matched) / 5.0, 1.0)
                item.category = self._detect_category(text)
                filtered.append(item)

        return filtered

    @staticmethod
    def _detect_category(text: str) -> NewsCategory:
        """Detect the most relevant news category from text content.

        Args:
            text: Lowercased combined title + description.

        Returns:
            Best matching NewsCategory.
        """
        best_category = NewsCategory.OTHER
        best_count = 0

        for category, patterns in _CATEGORY_PATTERNS.items():
            count = sum(1 for p in patterns if re.search(p, text, re.IGNORECASE))
            if count > best_count:
                best_count = count
                best_category = category

        return best_category

    def _store_items(self, items: List[NewsItem]) -> None:
        """Persist news items to SQLite.

        Args:
            items: List of NewsItem to insert.
        """
        conn = sqlite3.connect(self._db_path)
        try:
            for item in items:
                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO news_items
                        (title_hash, title, description, url, source_name,
                         source_type, category, published_at, fetched_at,
                         keywords_matched, relevance_score)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item.title_hash,
                            item.title,
                            item.description,
                            item.url,
                            item.source_name,
                            item.source_type.value,
                            item.category.value,
                            item.published_at.isoformat(),
                            item.fetched_at.isoformat(),
                            str(item.keywords_matched),
                            item.relevance_score,
                        ),
                    )
                except sqlite3.Error as exc:
                    logger.warning("rss_db_insert_error", error=str(exc))
            conn.commit()
            logger.info("rss_items_stored", count=len(items))
        finally:
            conn.close()

    def get_recent_items(
        self,
        limit: int = 50,
        category: Optional[NewsCategory] = None,
    ) -> List[NewsItem]:
        """Retrieve recent stored news items.

        Args:
            limit: Maximum number of items to return.
            category: Optional category filter.

        Returns:
            List of NewsItem from database, newest first.
        """
        conn = sqlite3.connect(self._db_path)
        try:
            if category:
                cursor = conn.execute(
                    """
                    SELECT title, description, url, source_name, source_type,
                           category, published_at, fetched_at, keywords_matched,
                           relevance_score
                    FROM news_items
                    WHERE category = ?
                    ORDER BY published_at DESC
                    LIMIT ?
                    """,
                    (category.value, limit),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT title, description, url, source_name, source_type,
                           category, published_at, fetched_at, keywords_matched,
                           relevance_score
                    FROM news_items
                    ORDER BY published_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )

            items: List[NewsItem] = []
            for row in cursor.fetchall():
                items.append(
                    NewsItem(
                        title=row[0],
                        description=row[1],
                        url=row[2],
                        source_name=row[3],
                        source_type=SignalSource(row[4]),
                        category=NewsCategory(row[5]),
                        published_at=datetime.fromisoformat(row[6]),
                        fetched_at=datetime.fromisoformat(row[7]),
                        relevance_score=row[9],
                    )
                )
            return items
        finally:
            conn.close()

    def cleanup_old(self, keep_days: int = 30) -> int:
        """Delete news items older than keep_days.

        Args:
            keep_days: Number of days to retain.

        Returns:
            Number of rows deleted.
        """
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute(
                """
                DELETE FROM news_items
                WHERE published_at < datetime('now', ? || ' days')
                """,
                (f"-{keep_days}",),
            )
            conn.commit()
            deleted = cursor.rowcount
            logger.info("rss_cleanup", deleted=deleted, keep_days=keep_days)
            return deleted
        finally:
            conn.close()
