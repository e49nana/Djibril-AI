"""Tests for Step 6 — claude_scorer.py validation."""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scoring.claude_scorer import ClaudeScorer
from utils.models import GeoScore, NewsItem, Urgency


class TestClaudeScorer:
    def setup_method(self) -> None:
        self.scorer = ClaudeScorer()

    def test_empty_items(self) -> None:
        result = self.scorer.score_headlines([])
        assert result.score == 0
        assert result.urgency == Urgency.LOW
        assert result.headlines_analyzed == 0

    def test_format_headlines(self) -> None:
        items = [
            NewsItem(title="Iran test headline", source_name="reuters"),
            NewsItem(title="Oil price surge", source_name="bbc", description="Crude rises on tensions"),
        ]
        text = self.scorer._format_headlines(items)
        assert "1. [reuters] Iran test headline" in text
        assert "2. [bbc] Oil price surge" in text
        assert "Crude rises on tensions" in text

    def test_build_cache_key_deterministic(self) -> None:
        items = [
            NewsItem(title="Headline A"),
            NewsItem(title="Headline B"),
        ]
        k1 = self.scorer._build_cache_key(items)
        k2 = self.scorer._build_cache_key(list(reversed(items)))
        assert k1 == k2  # Sorted, so order-independent

    def test_parse_response_valid(self) -> None:
        raw = json.dumps({
            "score": 7,
            "urgency": "high",
            "reasoning": "Iran military buildup near Strait of Hormuz.",
            "key_events": ["Naval deployment", "IRGC statement"],
            "oil_impact": "bullish",
        })
        result = self.scorer._parse_response(raw, headline_count=5)
        assert result.score == 7
        assert result.urgency == Urgency.HIGH
        assert result.oil_impact == "bullish"
        assert len(result.key_events) == 2
        assert result.headlines_analyzed == 5

    def test_parse_response_with_markdown_fences(self) -> None:
        raw = '```json\n{"score": -3, "urgency": "low", "reasoning": "De-escalation.", "key_events": [], "oil_impact": "bearish"}\n```'
        result = self.scorer._parse_response(raw, headline_count=2)
        assert result.score == -3
        assert result.oil_impact == "bearish"

    def test_parse_response_clamps_values(self) -> None:
        raw = json.dumps({"score": 99, "urgency": "unknown", "reasoning": "x", "key_events": [], "oil_impact": "invalid"})
        result = self.scorer._parse_response(raw, headline_count=1)
        assert result.score == 10  # Clamped
        assert result.urgency == Urgency.LOW  # Fallback
        assert result.oil_impact == "neutral"  # Fallback

    def test_fallback_score_tension(self) -> None:
        items = [
            NewsItem(title="Iran launches missile strike on oil facility", source_name="x"),
            NewsItem(title="Military escalation blockade threat", source_name="y"),
        ]
        result = self.scorer._fallback_score(items)
        assert result.score > 0
        assert result.model_used == "fallback-keyword"

    def test_fallback_score_deescalation(self) -> None:
        items = [
            NewsItem(title="Iran peace agreement deal signed diplomacy", source_name="x"),
        ]
        result = self.scorer._fallback_score(items)
        assert result.score < 0

    def test_cache_hit(self) -> None:
        items = [NewsItem(title="Cache test headline")]
        fake_score = GeoScore(score=5, urgency=Urgency.MEDIUM, reasoning="cached")
        import time
        key = self.scorer._build_cache_key(items)
        self.scorer._cache[key] = (fake_score, time.time())

        result = self.scorer.score_headlines(items, use_cache=True)
        assert result.score == 5
        assert result.reasoning == "cached"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
