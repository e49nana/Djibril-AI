"""Tests for Step 8 — sentiment_analyzer.py validation."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scoring.sentiment_analyzer import SentimentAnalyzer, _BULLISH_WORDS, _BEARISH_WORDS


class TestSentimentAnalyzer:
    def setup_method(self) -> None:
        self.analyzer = SentimentAnalyzer()

    def test_score_text_bullish(self) -> None:
        text = "Oil prices surge amid supply disruption and escalation threat"
        score = self.analyzer._score_text(text)
        assert score > 0

    def test_score_text_bearish(self) -> None:
        text = "Oil crashes as peace deal agreement leads to production increase"
        score = self.analyzer._score_text(text)
        assert score < 0

    def test_score_text_neutral(self) -> None:
        text = "The weather is nice today, nothing happening"
        score = self.analyzer._score_text(text)
        assert score == 0.0

    def test_score_text_bounds(self) -> None:
        # All bullish words
        text = " ".join(_BULLISH_WORDS)
        score = self.analyzer._score_text(text)
        assert -1.0 <= score <= 1.0

    def test_word_lists_populated(self) -> None:
        assert len(_BULLISH_WORDS) >= 10
        assert len(_BEARISH_WORDS) >= 10

    def test_analyze_runs_without_keys(self) -> None:
        """When no API keys are set, analyze should still return a valid score."""
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(self.analyzer.analyze())
            assert -1.0 <= result.score <= 1.0
            assert result.computed_at is not None
        finally:
            loop.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
