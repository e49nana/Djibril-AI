"""
Djibril AI — NewsAPI Fetcher

Fetches Iran/oil/geopolitical headlines from NewsAPI.org.
Features: tenacity retry, SQLite cache (Redis optional), cross-source dedup,
async queue emission.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

try:
    from ..utils.config import get_settings
    from ..utils.logger import get_logger, timed
    from ..utils.models import NewsCategory, NewsItem, SignalSource
except ImportError:
    from utils.config import get_settings
    from utils.logger import get_logger, timed
    from utils.models import NewsCategory, NewsItem, SignalSource

logger = get_logger(__name__)

_NEWSAPI_URL = "https://newsapi.org/v2/everything"

# Specialized query sets for comprehensive Iran/oil coverage
_QUERY_SETS: list[str] = [
    "Iran oil sanctions",
    "Strait of Hormuz",
    "OPEC crude oil production",
    "Iran military Gulf",
    "oil tanker Middle East",
    "Iran nuclear JCPOA",
    "Houthi Red Sea shipping",
    "WTI Brent crude price",
]


class NewsFetcher:
    """NewsAPI collector with retry, caching, and deduplication.

    Uses SQLite as the default cache backend. Optionally uses Redis
    if REDIS_URL is set in the environment.
    """

    def __init__(
        self,
        db_path: str = "djibril.db",
        event_queue: Optional[asyncio.Queue[NewsItem]] = None,
    ) -> None:
        self._settings = get_settings()
        self._db_path = db_path
        self._event_queue = event_queue
        self._redis: Any = None
        self._seen_hashes: set[str] = set()
        self._init_cache_db()
        self._try_init_redis()

    def _init_cache_db(self) -> None:
        """Create the newsapi_cache table for response caching."""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS newsapi_cache (
                    query_hash TEXT PRIMARY KEY,
                    response_json TEXT NOT NULL,
                    cached_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS newsapi_seen (
                    title_hash TEXT PRIMARY KEY,
                    first_seen_at TEXT NOT NULL
                )
            """)
            conn.commit()
            cursor = conn.execute("SELECT title_hash FROM newsapi_seen")
            self._seen_hashes = {row[0] for row in cursor.fetchall()}
        finally:
            conn.close()

    def _try_init_redis(self) -> None:
        """Attempt to connect to Redis for caching. Silent fail to SQLite."""
        redis_url = self._settings.database.redis_url
        if not redis_url:
            return
        try:
            import redis as redis_lib
            self._redis = redis_lib.from_url(redis_url, decode_responses=True)
            self._redis.ping()
            logger.info("newsapi_redis_connected")
        except Exception as exc:
            logger.info("newsapi_redis_unavailable", error=str(exc))
            self._redis = None

    @timed
    async def fetch_all(self) -> List[NewsItem]:
        """Run all query sets and return deduplicated, relevant news items.

        Returns:
            List of unique NewsItem objects matching geopolitical criteria.
        """
        api_key = self._settings.newsapi.api_key
        if not api_key:
            logger.warning("newsapi_no_api_key")
            return []

        timeout = aiohttp.ClientTimeout(total=30)
        all_items: List[NewsItem] = []

        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [
                self._fetch_query(session, query, api_key)
                for query in _QUERY_SETS
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(
                    "newsapi_query_failed",
                    query=_QUERY_SETS[i],
                    error=str(result),
                )
                continue
            all_items.extend(result)

        # Cross-source deduplication
        unique = self._deduplicate(all_items)

        # Emit to event queue
        if self._event_queue and unique:
            for item in unique:
                try:
                    self._event_queue.put_nowait(item)
                except asyncio.QueueFull:
                    logger.warning("newsapi_queue_full")
                    break

        logger.info(
            "newsapi_fetch_complete",
            total_raw=len(all_items),
            unique=len(unique),
        )
        return unique

    async def _fetch_query(
        self,
        session: aiohttp.ClientSession,
        query: str,
        api_key: str,
    ) -> List[NewsItem]:
        """Fetch a single query from NewsAPI with caching.

        Args:
            session: aiohttp session.
            query: Search query string.
            api_key: NewsAPI key.

        Returns:
            Parsed NewsItem list.
        """
        # Check cache first
        cached = self._get_cached(query)
        if cached is not None:
            logger.debug("newsapi_cache_hit", query=query)
            return cached

        # Fetch from API with retry
        articles = await self._api_call(session, query, api_key)

        items = self._parse_articles(articles, query)

        # Cache the result
        self._set_cached(query, items)

        return items

    @retry(
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _api_call(
        self,
        session: aiohttp.ClientSession,
        query: str,
        api_key: str,
    ) -> List[Dict[str, Any]]:
        """Make the actual NewsAPI HTTP request with tenacity retry.

        Args:
            session: aiohttp session.
            query: Search query.
            api_key: API key.

        Returns:
            List of raw article dicts.
        """
        params = {
            "q": query,
            "apiKey": api_key,
            "language": self._settings.newsapi.language,
            "sortBy": self._settings.newsapi.sort_by,
            "pageSize": self._settings.newsapi.page_size,
        }

        async with session.get(_NEWSAPI_URL, params=params) as resp:
            if resp.status == 429:
                logger.warning("newsapi_rate_limited", query=query)
                raise aiohttp.ClientError("Rate limited")
            if resp.status != 200:
                text = await resp.text()
                logger.warning("newsapi_error", status=resp.status, body=text[:200])
                return []

            data = await resp.json()

        if data.get("status") != "ok":
            logger.warning("newsapi_bad_status", response=data.get("message", ""))
            return []

        return data.get("articles", [])

    def _parse_articles(
        self, articles: List[Dict[str, Any]], query: str
    ) -> List[NewsItem]:
        """Convert raw NewsAPI article dicts to NewsItem.

        Args:
            articles: Raw article dicts from API.
            query: The query that produced these results.

        Returns:
            Parsed NewsItem list.
        """
        items: List[NewsItem] = []
        keywords = self._settings.GEO_KEYWORDS

        for article in articles:
            title = (article.get("title") or "").strip()
            if not title or title == "[Removed]":
                continue

            description = (article.get("description") or "").strip()
            text = f"{title} {description}".lower()

            # Check keyword relevance
            matched_kw = [kw for kw in keywords if kw in text]
            if not matched_kw:
                continue

            # Parse published date
            pub_str = article.get("publishedAt", "")
            try:
                pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pub_dt = datetime.now(timezone.utc)

            source_name = ""
            if isinstance(article.get("source"), dict):
                source_name = article["source"].get("name", "")

            items.append(
                NewsItem(
                    title=title,
                    description=description[:500],
                    url=article.get("url", ""),
                    source_name=source_name or "newsapi",
                    source_type=SignalSource.NEWSAPI,
                    published_at=pub_dt,
                    fetched_at=datetime.now(timezone.utc),
                    keywords_matched=matched_kw,
                    relevance_score=min(len(matched_kw) / 5.0, 1.0),
                )
            )

        return items

    def _deduplicate(self, items: List[NewsItem]) -> List[NewsItem]:
        """Remove items already seen cross-source.

        Args:
            items: Full list of fetched items.

        Returns:
            Only new items.
        """
        new_items: List[NewsItem] = []
        conn = sqlite3.connect(self._db_path)
        try:
            for item in items:
                h = item.title_hash
                if h not in self._seen_hashes:
                    self._seen_hashes.add(h)
                    new_items.append(item)
                    conn.execute(
                        "INSERT OR IGNORE INTO newsapi_seen (title_hash, first_seen_at) VALUES (?, ?)",
                        (h, datetime.now(timezone.utc).isoformat()),
                    )
            conn.commit()
        finally:
            conn.close()
        return new_items

    def _get_cached(self, query: str) -> Optional[List[NewsItem]]:
        """Check cache for a recent response to this query.

        Args:
            query: Search query string.

        Returns:
            Cached NewsItem list or None if cache miss/expired.
        """
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        cache_ttl = 300  # 5 minutes

        # Try Redis first
        if self._redis:
            try:
                cached = self._redis.get(f"newsapi:{query_hash}")
                if cached:
                    return [NewsItem(**item) for item in json.loads(cached)]
            except Exception:
                pass

        # Fallback to SQLite
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute(
                "SELECT response_json, cached_at FROM newsapi_cache WHERE query_hash = ?",
                (query_hash,),
            )
            row = cursor.fetchone()
            if row and (time.time() - row[1]) < cache_ttl:
                return [NewsItem(**item) for item in json.loads(row[0])]
        finally:
            conn.close()

        return None

    def _set_cached(self, query: str, items: List[NewsItem]) -> None:
        """Store query results in cache.

        Args:
            query: The search query.
            items: Parsed items to cache.
        """
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        serialized = json.dumps([item.model_dump(mode="json") for item in items])

        # Try Redis
        if self._redis:
            try:
                self._redis.setex(f"newsapi:{query_hash}", 300, serialized)
                return
            except Exception:
                pass

        # Fallback to SQLite
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO newsapi_cache (query_hash, response_json, cached_at)
                VALUES (?, ?, ?)
                """,
                (query_hash, serialized, time.time()),
            )
            conn.commit()
        finally:
            conn.close()
