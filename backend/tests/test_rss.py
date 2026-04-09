"""Tests for Step 3 — rss_aggregator.py validation."""

import asyncio
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collectors.rss_aggregator import RSSAggregator
from utils.models import NewsCategory, NewsItem


class TestRSSAggregator:
    def setup_method(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.agg = RSSAggregator(db_path=self.tmp.name)

    def teardown_method(self) -> None:
        os.unlink(self.tmp.name)

    def test_db_initialized(self) -> None:
        conn = sqlite3.connect(self.tmp.name)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='news_items'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_deduplication(self) -> None:
        items = [
            NewsItem(title="Iran sanctions update", source_name="reuters"),
            NewsItem(title="Iran sanctions update", source_name="bbc"),  # duplicate
            NewsItem(title="Oil price rises", source_name="aljazeera"),
        ]
        result = self.agg._deduplicate(items)
        assert len(result) == 2

    def test_keyword_filtering(self) -> None:
        items = [
            NewsItem(
                title="Iran threatens to close Strait of Hormuz",
                description="Military tensions rise in Persian Gulf",
            ),
            NewsItem(
                title="Local weather update in London",
                description="Rain expected tomorrow",
            ),
        ]
        filtered = self.agg._filter_by_keywords(items)
        assert len(filtered) == 1
        assert "iran" in filtered[0].keywords_matched
        assert filtered[0].relevance_score > 0

    def test_category_detection(self) -> None:
        assert (
            RSSAggregator._detect_category("military strike on oil facility missile")
            == NewsCategory.MILITARY
        )
        assert (
            RSSAggregator._detect_category("new sanctions imposed on iran embargo")
            == NewsCategory.SANCTIONS
        )
        assert (
            RSSAggregator._detect_category("opec crude oil barrel production")
            == NewsCategory.ENERGY
        )

    def test_store_and_retrieve(self) -> None:
        items = [
            NewsItem(
                title="Iran oil sanctions headline",
                description="Test desc",
                source_name="test",
                category=NewsCategory.SANCTIONS,
                keywords_matched=["iran", "oil", "sanctions"],
                relevance_score=0.6,
            )
        ]
        self.agg._store_items(items)
        retrieved = self.agg.get_recent_items(limit=10)
        assert len(retrieved) == 1
        assert retrieved[0].title == "Iran oil sanctions headline"

    def test_retrieve_by_category(self) -> None:
        items = [
            NewsItem(title="Military action", category=NewsCategory.MILITARY, source_name="a"),
            NewsItem(title="Sanctions news", category=NewsCategory.SANCTIONS, source_name="b"),
        ]
        self.agg._store_items(items)
        military = self.agg.get_recent_items(limit=10, category=NewsCategory.MILITARY)
        assert len(military) == 1
        assert military[0].category == NewsCategory.MILITARY

    def test_cleanup_old(self) -> None:
        # Insert an item, cleanup should not crash
        items = [NewsItem(title="Old news iran", source_name="x", keywords_matched=["iran"])]
        self.agg._store_items(items)
        deleted = self.agg.cleanup_old(keep_days=0)
        # Even if 0 deleted (just inserted), shouldn't error
        assert isinstance(deleted, int)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
