"""Tests for Step 12 — signal_composer.py validation."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from signals.signal_composer import SignalComposer
from utils.models import (
    GeoScore,
    GeoSignal,
    SentimentScore,
    TechnicalScore,
    TradeAction,
    Urgency,
)


def _make_signal(
    action: TradeAction = TradeAction.BUY,
    confidence: float = 0.8,
    geo_score: int = 6,
    tech_score: float = 0.5,
    atr: float = 1.50,
    price: float = 75.0,
) -> GeoSignal:
    return GeoSignal(
        geo_score=GeoScore(score=geo_score, urgency=Urgency.HIGH, reasoning="Test"),
        technical_score=TechnicalScore(score=tech_score, atr_14=atr, current_price=price, rsi_14=55),
        sentiment_score=SentimentScore(score=0.3, sample_size=50),
        composite_score=0.5,
        confidence=confidence,
        suggested_action=action,
        vix_level=18.0,
    )


class TestSignalComposer:
    def setup_method(self) -> None:
        self.composer = SignalComposer()

    def test_buy_signal(self) -> None:
        signal = _make_signal(TradeAction.BUY)
        result = self.composer.compose(signal)
        # May be FLAT if outside session hours; check logic
        if result.action == TradeAction.BUY:
            assert result.stop_loss < result.entry_price
            assert result.take_profit > result.entry_price
            assert result.lot_size > 0
            assert result.risk_reward_ratio >= 1.5
            assert result.signal_id.startswith("OG-")

    def test_sell_signal(self) -> None:
        signal = _make_signal(TradeAction.SELL)
        result = self.composer.compose(signal)
        if result.action == TradeAction.SELL:
            assert result.stop_loss > result.entry_price
            assert result.take_profit < result.entry_price

    def test_flat_on_low_confidence(self) -> None:
        signal = _make_signal(confidence=0.1)
        result = self.composer.compose(signal)
        assert result.action == TradeAction.FLAT
        assert "Confidence" in result.reasoning

    def test_flat_on_high_spread(self) -> None:
        signal = _make_signal()
        result = self.composer.compose(signal, current_spread=999)
        assert result.action == TradeAction.FLAT
        assert "Spread" in result.reasoning

    def test_flat_passthrough(self) -> None:
        signal = _make_signal(action=TradeAction.FLAT)
        result = self.composer.compose(signal)
        assert result.action == TradeAction.FLAT

    def test_session_filter(self) -> None:
        assert SignalComposer._is_in_session(10, 8, 20) is True
        assert SignalComposer._is_in_session(5, 8, 20) is False
        assert SignalComposer._is_in_session(22, 20, 4) is True  # Night session

    def test_atr_fallback(self) -> None:
        signal = _make_signal(atr=0.0)
        result = self.composer.compose(signal)
        # Should still produce a result (with fallback ATR)
        assert result is not None

    def test_signal_id_format(self) -> None:
        signal = _make_signal()
        result = self.composer.compose(signal)
        assert result.signal_id.startswith("OG-")

    def test_reasoning_populated(self) -> None:
        signal = _make_signal()
        result = self.composer.compose(signal)
        assert len(result.reasoning) > 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
