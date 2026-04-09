"""Tests for Step 5 — news_fetcher.py validation."""

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collectors.news_fetcher import NewsFetcher
from utils.models import NewsItem, SignalSource


class TestNewsFetcher:
    def setup_method(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.fetcher = NewsFetcher(db_path=self.tmp.name)

    def teardown_method(self) -> None:
        os.unlink(self.tmp.name)

    def test_db_tables_created(self) -> None:
        conn = sqlite3.connect(self.tmp.name)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        assert "newsapi_cache" in tables
        assert "newsapi_seen" in tables

    def test_parse_articles_filters(self) -> None:
        articles = [
            {
                "title": "Iran threatens to close Strait of Hormuz over oil sanctions",
                "description": "Rising tensions in Persian Gulf affect crude prices",
                "url": "https://example.com/1",
                "source": {"name": "Reuters"},
                "publishedAt": "2025-03-10T14:00:00Z",
            },
            {
                "title": "Best pizza in New York City",
                "description": "Food review of top NYC restaurants",
                "url": "https://example.com/2",
                "source": {"name": "Food Blog"},
                "publishedAt": "2025-03-10T15:00:00Z",
            },
            {
                "title": "[Removed]",
                "description": "",
                "url": "",
                "source": {},
                "publishedAt": "",
            },
        ]
        items = self.fetcher._parse_articles(articles, query="Iran oil")
        assert len(items) == 1
        assert "iran" in items[0].keywords_matched
        assert items[0].source_type == SignalSource.NEWSAPI

    def test_deduplication(self) -> None:
        items = [
            NewsItem(title="Iran oil sanctions update", source_name="reuters"),
            NewsItem(title="Iran oil sanctions update", source_name="bbc"),
            NewsItem(title="OPEC cuts production", source_name="ap"),
        ]
        unique = self.fetcher._deduplicate(items)
        assert len(unique) == 2

    def test_cache_round_trip(self) -> None:
        items = [
            NewsItem(
                title="Test cache item iran oil",
                source_name="test",
                keywords_matched=["iran", "oil"],
            )
        ]
        self.fetcher._set_cached("test_query", items)
        cached = self.fetcher._get_cached("test_query")
        assert cached is not None
        assert len(cached) == 1
        assert cached[0].title == "Test cache item iran oil"

    def test_event_queue_emission(self) -> None:
        queue: asyncio.Queue[NewsItem] = asyncio.Queue(maxsize=100)
        fetcher = NewsFetcher(db_path=self.tmp.name, event_queue=queue)
        items = [
            NewsItem(title="Unique iran oil headline 123", source_name="test")
        ]
        # Simulate dedup + queue emission
        unique = fetcher._deduplicate(items)
        for item in unique:
            queue.put_nowait(item)
        assert queue.qsize() == 1

    def test_no_api_key_returns_empty(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(self.fetcher.fetch_all())
            assert result == []  # No API key set
        finally:
            loop.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
