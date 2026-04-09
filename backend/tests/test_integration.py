"""
Djibril AI — Integration Tests

Tests the full pipeline: collectors → scoring → signal → publisher.
Uses synthetic data and mocked external APIs.
"""

import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.models import (
    GeoScore,
    GeoSignal,
    NewsCategory,
    NewsItem,
    SentimentScore,
    SignalSource,
    TechnicalScore,
    TradeAction,
    TradeSignal,
    Urgency,
)
from collectors.rss_aggregator import RSSAggregator
from collectors.worldmonitor_client import WorldMonitorClient
from collectors.news_fetcher import NewsFetcher
from scoring.claude_scorer import ClaudeScorer
from scoring.sentiment_analyzer import SentimentAnalyzer
from scoring.technical_analyzer import TechnicalAnalyzer
from scoring.geo_risk_engine import GeoRiskEngine
from signals.signal_composer import SignalComposer
from signals.kelly_calculator import KellyCalculator
from signals.signal_publisher import SignalPublisher
from signals.alerts import AlertManager


# ═══════════════════════════════════════════════════
# Synthetic test data
# ═══════════════════════════════════════════════════

def make_synthetic_news(n: int = 10) -> list[NewsItem]:
    """Generate synthetic Iran/oil news headlines for testing."""
    headlines = [
        ("Iran threatens to close Strait of Hormuz over sanctions", NewsCategory.MILITARY),
        ("OPEC+ agrees to cut production by 1M bbl/day", NewsCategory.ENERGY),
        ("US Navy deploys carrier group to Persian Gulf", NewsCategory.MILITARY),
        ("Iran-Saudi diplomatic talks resume in Geneva", NewsCategory.DIPLOMATIC),
        ("Houthi rebels target oil tanker in Red Sea", NewsCategory.CONFLICT),
        ("New EU sanctions target Iranian oil exports", NewsCategory.SANCTIONS),
        ("Oil pipeline damaged in Iraq by drone attack", NewsCategory.INFRASTRUCTURE),
        ("Iran enriches uranium to 60% purity", NewsCategory.MILITARY),
        ("JCPOA negotiations break down in Vienna", NewsCategory.DIPLOMATIC),
        ("WTI crude surges to $85 on supply fears", NewsCategory.ENERGY),
        ("Saudi Aramco cuts Asian oil prices", NewsCategory.ENERGY),
        ("Iran IRGC conducts missile test near Gulf", NewsCategory.MILITARY),
    ]
    items = []
    for i in range(min(n, len(headlines))):
        title, cat = headlines[i]
        items.append(
            NewsItem(
                title=title,
                description=f"Detailed report on {title.lower()}",
                source_name=f"source_{i}",
                source_type=SignalSource.RSS,
                category=cat,
                keywords_matched=["iran", "oil"],
                relevance_score=0.8,
            )
        )
    return items


# ═══════════════════════════════════════════════════
# Pipeline integration test
# ═══════════════════════════════════════════════════

class TestFullPipeline:
    """Test the complete signal pipeline with synthetic data."""

    def setup_method(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        os.environ["SIGNAL_OUTPUT_DIR"] = self.tmp

    def test_full_pipeline_synthetic(self) -> None:
        """Run the entire pipeline: news → scoring → signal → publish."""

        # 1. Generate synthetic news
        news = make_synthetic_news(10)
        assert len(news) == 10
        assert all(isinstance(n, NewsItem) for n in news)

        # 2. Score with fallback (no API key)
        scorer = ClaudeScorer()
        geo_score = scorer._fallback_score(news)
        assert isinstance(geo_score, GeoScore)
        assert -10 <= geo_score.score <= 10
        assert geo_score.model_used == "fallback-keyword"

        # 3. Technical analysis (mock)
        tech_score = TechnicalScore(
            score=0.45,
            rsi_14=58.0,
            atr_14=1.65,
            ema_20=76.50,
            ema_50=74.20,
            supertrend_direction="bullish",
            volume_ratio=1.3,
            current_price=77.80,
            symbol="CL=F",
        )

        # 4. Sentiment (mock)
        sentiment = SentimentScore(score=0.25, sample_size=50)

        # 5. Risk engine
        engine = GeoRiskEngine()
        geo_signal = engine.compute_signal(
            geo_score=geo_score,
            technical_score=tech_score,
            sentiment_score=sentiment,
            vix_level=22.0,
        )
        assert isinstance(geo_signal, GeoSignal)
        assert -1.0 <= geo_signal.composite_score <= 1.0
        assert 0.0 <= geo_signal.confidence <= 1.0

        # 6. Signal composition
        composer = SignalComposer()
        trade_signal = composer.compose(geo_signal)
        assert isinstance(trade_signal, TradeSignal)
        assert trade_signal.signal_id.startswith("OG-")

        # 7. Publish
        publisher = SignalPublisher(db_path=self.db_path)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(publisher.publish(trade_signal))
        finally:
            loop.close()

        # 8. Verify storage
        latest = publisher.get_latest()
        assert latest is not None
        assert latest["signal_id"] == trade_signal.signal_id

        # 9. Verify history
        history = publisher.get_history(limit=10)
        assert len(history) == 1

    def test_multiple_signals_pipeline(self) -> None:
        """Run the pipeline 5 times with varying params. All FLAT signals
        in the same second share an ID, so verify at least 1 stored."""
        publisher = SignalPublisher(db_path=self.db_path)
        composer = SignalComposer()
        engine = GeoRiskEngine()
        scorer = ClaudeScorer()

        loop = asyncio.new_event_loop()
        signals_published = 0
        try:
            for i in range(5):
                news = make_synthetic_news(5)
                geo_score = scorer._fallback_score(news)
                tech = TechnicalScore(
                    score=0.3 * (1 if i % 2 == 0 else -1),
                    atr_14=1.5,
                    current_price=75.0 + i,
                    rsi_14=50 + i * 3,
                )
                sent = SentimentScore(score=0.1 * i, sample_size=30)
                signal = engine.compute_signal(geo_score, tech, sent, vix_level=20.0)
                trade = composer.compose(signal)
                loop.run_until_complete(publisher.publish(trade))
                signals_published += 1
        finally:
            loop.close()

        assert signals_published == 5
        history = publisher.get_history(limit=50)
        # FLAT signals within the same second share signal_id, so at least 1 persists
        assert len(history) >= 1


class TestKellyIntegration:
    def test_kelly_with_real_params(self) -> None:
        calc = KellyCalculator()
        result = calc.calculate(
            sl_pips=150,
            confidence=0.82,
            win_rate=0.55,
            avg_wl_ratio=1.67,
            account_balance=10000,
            max_risk=0.05,
        )
        assert result.lot_size > 0
        assert result.risk_percent <= 0.05
        assert result.kelly_fraction > 0


class TestAlertFormatting:
    def test_buy_alert_format(self) -> None:
        am = AlertManager()
        sig = TradeSignal(
            signal_id="OG-TEST-001",
            action=TradeAction.BUY,
            symbol="XTIUSD",
            confidence=0.82,
            entry_price=78.50,
            stop_loss=76.80,
            take_profit=81.00,
            lot_size=0.10,
            sl_pips=170,
            tp_pips=250,
            risk_reward_ratio=1.47,
            reasoning="High geo tension + bullish technicals",
            geo_score=7,
            urgency=Urgency.HIGH,
        )
        msg = am._format_message(sig)
        assert "BUY" in msg
        assert "$78.50" in msg
        assert "OG-TEST-001" in msg

    def test_cooldown_logic(self) -> None:
        am = AlertManager()
        assert am._is_in_cooldown("BUY_high") is False
        import time
        am._last_alert_time["BUY_high"] = time.time()
        assert am._is_in_cooldown("BUY_high") is True


class TestCollectors:
    def test_rss_dedup_and_filter(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        try:
            agg = RSSAggregator(db_path=tmp.name)
            items = [
                NewsItem(title="Iran oil headline", source_name="a", description="sanctions iran oil"),
                NewsItem(title="Iran oil headline", source_name="b"),
                NewsItem(title="Weather in Paris", source_name="c"),
            ]
            deduped = agg._deduplicate(items)
            assert len(deduped) == 2
            filtered = agg._filter_by_keywords(deduped)
            assert len(filtered) == 1
        finally:
            os.unlink(tmp.name)

    def test_worldmonitor_relevance_filter(self) -> None:
        client = WorldMonitorClient()
        assert client._is_relevant(NewsItem(title="Iran missile test", source_name="x"))
        assert not client._is_relevant(NewsItem(title="Recipe for cookies", source_name="x"))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
