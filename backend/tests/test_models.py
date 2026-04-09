"""Tests for Step 1 — config.py and models.py validation."""

import os
import sys
from datetime import datetime, timezone

import pytest

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.config import Settings, get_settings
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
    WSMessage,
    WSMessageType,
)


class TestSettings:
    def test_settings_instantiation(self) -> None:
        s = Settings()
        assert s.trading.max_risk_per_trade == 0.05
        assert s.trading.geo_weight + s.trading.technical_weight + s.trading.sentiment_weight == 1.0
        assert s.anthropic.model == "claude-opus-4-6"

    def test_singleton(self) -> None:
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_rss_feeds_populated(self) -> None:
        s = Settings()
        assert len(s.RSS_FEEDS) >= 5
        assert "aljazeera" in s.RSS_FEEDS

    def test_geo_keywords_populated(self) -> None:
        s = Settings()
        assert "iran" in s.GEO_KEYWORDS
        assert "strait of hormuz" in s.GEO_KEYWORDS


class TestNewsItem:
    def test_creation(self) -> None:
        item = NewsItem(title="Iran threatens Strait of Hormuz closure", source_name="Reuters")
        assert item.title_hash  # computed field
        assert len(item.title_hash) == 16

    def test_dedup_hash_consistency(self) -> None:
        a = NewsItem(title="Test headline")
        b = NewsItem(title="test headline")  # case insensitive
        assert a.title_hash == b.title_hash

    def test_category_enum(self) -> None:
        item = NewsItem(title="x", category=NewsCategory.MILITARY)
        assert item.category == NewsCategory.MILITARY


class TestGeoScore:
    def test_valid_score(self) -> None:
        gs = GeoScore(score=7, urgency=Urgency.HIGH, reasoning="Tensions rising")
        assert gs.score == 7
        assert gs.model_used == "claude-opus-4-6"

    def test_score_bounds(self) -> None:
        with pytest.raises(Exception):
            GeoScore(score=15)  # > 10


class TestTradeSignal:
    def test_full_signal(self) -> None:
        ts = TradeSignal(
            signal_id="SIG-001",
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
        assert ts.action == TradeAction.BUY
        assert ts.signal_id == "SIG-001"

    def test_json_serialization(self) -> None:
        ts = TradeSignal(signal_id="SIG-002", action=TradeAction.SELL)
        data = ts.model_dump_json()
        assert "SIG-002" in data
        assert "SELL" in data


class TestWSMessage:
    def test_heartbeat(self) -> None:
        msg = WSMessage(type=WSMessageType.HEARTBEAT)
        assert msg.type == WSMessageType.HEARTBEAT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
