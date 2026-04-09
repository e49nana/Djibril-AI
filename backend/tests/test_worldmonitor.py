"""Tests for Step 4 — worldmonitor_client.py validation."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collectors.worldmonitor_client import WorldMonitorClient, _REGION_KEYWORDS
from utils.models import NewsCategory, NewsItem, SignalSource


class TestWorldMonitorClient:
    def setup_method(self) -> None:
        self.client = WorldMonitorClient()

    def test_is_relevant_positive(self) -> None:
        item = NewsItem(title="Iran threatens Strait of Hormuz", source_name="wm")
        assert self.client._is_relevant(item) is True

    def test_is_relevant_negative(self) -> None:
        item = NewsItem(title="Weather in London is nice today", source_name="wm")
        assert self.client._is_relevant(item) is False

    def test_extract_keywords(self) -> None:
        item = NewsItem(
            title="Iran IRGC launches missile near Saudi oil facility",
            description="Oil prices surge on fears of supply disruption",
        )
        kws = self.client._extract_keywords(item)
        assert "iran" in kws
        assert "oil" in kws
        assert "irgc" in kws

    def test_normalize_api_events(self) -> None:
        events = [
            {
                "title": "Iran deploys naval forces near Strait of Hormuz",
                "description": "Military buildup in Persian Gulf raises oil supply concerns",
                "category": "military",
                "date": "2025-03-10T14:00:00Z",
                "url": "https://worldmonitor.app/event/123",
            },
            {
                "title": "New restaurant opens in Paris",
                "description": "French cuisine news",
                "category": "other",
                "date": "2025-03-10T12:00:00Z",
            },
        ]
        items = self.client._normalize_api_events(events)
        assert len(items) == 1
        assert items[0].category == NewsCategory.MILITARY
        assert items[0].source_type == SignalSource.WORLDMONITOR

    def test_parse_html_response(self) -> None:
        html = """
        <html><body>
        <h2>Iran threatens to block oil tankers in Strait of Hormuz</h2>
        <h2>New EU sanctions target Iranian oil exports</h2>
        <h2>Local soccer match results in Manchester</h2>
        </body></html>
        """
        items = self.client._parse_html_response(html, limit=10)
        assert len(items) == 2  # Only geo-relevant ones

    def test_parse_json_response(self) -> None:
        import json
        data = json.dumps({
            "events": [
                {"title": "OPEC cuts crude oil production target", "category": "energy"},
                {"title": "Cat video goes viral", "category": "other"},
            ]
        })
        items = self.client._parse_json_response(data, limit=10)
        assert len(items) == 1  # Only "OPEC cuts" is relevant
        assert items[0].category == NewsCategory.ENERGY

    def test_region_keywords_populated(self) -> None:
        assert len(_REGION_KEYWORDS) >= 10
        assert "iran" in _REGION_KEYWORDS
        assert "strait of hormuz" in _REGION_KEYWORDS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
