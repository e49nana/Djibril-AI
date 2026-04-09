"""Tests for Step 10 — geo_risk_engine.py validation."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scoring.geo_risk_engine import GeoRiskEngine
from utils.models import (
    GeoScore,
    SentimentScore,
    TechnicalScore,
    TradeAction,
    Urgency,
)


def _make_geo(score: int = 5, urgency: Urgency = Urgency.MEDIUM) -> GeoScore:
    return GeoScore(score=score, urgency=urgency, reasoning="test")


def _make_tech(score: float = 0.5) -> TechnicalScore:
    return TechnicalScore(score=score, rsi_14=55, atr_14=1.5, current_price=75.0)


def _make_sent(score: float = 0.3) -> SentimentScore:
    return SentimentScore(score=score, sample_size=50)


class TestGeoRiskEngine:
    def setup_method(self) -> None:
        self.engine = GeoRiskEngine()

    def test_bullish_signal(self) -> None:
        signal = self.engine.compute_signal(
            _make_geo(7, Urgency.HIGH),
            _make_tech(0.6),
            _make_sent(0.4),
            vix_level=18.0,
        )
        assert signal.composite_score > 0
        assert signal.suggested_action == TradeAction.BUY
        assert signal.confidence > 0

    def test_bearish_signal(self) -> None:
        signal = self.engine.compute_signal(
            _make_geo(-6, Urgency.MEDIUM),
            _make_tech(-0.5),
            _make_sent(-0.3),
            vix_level=18.0,
        )
        assert signal.composite_score < 0
        assert signal.suggested_action == TradeAction.SELL

    def test_flat_on_conflict(self) -> None:
        signal = self.engine.compute_signal(
            _make_geo(5),       # bullish geo
            _make_tech(-0.6),   # bearish tech
            _make_sent(0.0),    # neutral sentiment
            vix_level=20.0,
        )
        # Conflict should reduce confidence
        conflict_flags = [f for f in signal.risk_flags if f.flag_type == "signal_conflict"]
        assert len(conflict_flags) >= 1

    def test_vix_extreme_reduces_confidence(self) -> None:
        normal = self.engine.compute_signal(
            _make_geo(5), _make_tech(0.5), _make_sent(0.3), vix_level=15.0
        )
        extreme = self.engine.compute_signal(
            _make_geo(5), _make_tech(0.5), _make_sent(0.3), vix_level=40.0
        )
        assert extreme.confidence < normal.confidence

    def test_vix_flag_added(self) -> None:
        signal = self.engine.compute_signal(
            _make_geo(3), _make_tech(0.2), _make_sent(0.1), vix_level=30.0
        )
        vix_flags = [f for f in signal.risk_flags if f.flag_type == "high_vix"]
        assert len(vix_flags) == 1

    def test_critical_urgency_flag(self) -> None:
        signal = self.engine.compute_signal(
            _make_geo(9, Urgency.CRITICAL),
            _make_tech(0.3),
            _make_sent(0.2),
            vix_level=20.0,
        )
        crit_flags = [f for f in signal.risk_flags if f.flag_type == "critical_geo_event"]
        assert len(crit_flags) == 1

    def test_low_liquidity_flag(self) -> None:
        tech = _make_tech(0.3)
        tech.volume_ratio = 0.3
        signal = self.engine.compute_signal(
            _make_geo(3), tech, _make_sent(0.1), vix_level=20.0
        )
        liq_flags = [f for f in signal.risk_flags if f.flag_type == "low_liquidity"]
        assert len(liq_flags) == 1

    def test_detect_conflicts_geo_vs_tech(self) -> None:
        flags = GeoRiskEngine._detect_conflicts(0.6, -0.5, 0.0)
        assert len(flags) >= 1
        assert flags[0].flag_type == "signal_conflict"

    def test_vix_confidence_modifier(self) -> None:
        assert GeoRiskEngine._vix_confidence_modifier(10) == 1.2
        assert 0.8 <= GeoRiskEngine._vix_confidence_modifier(20) <= 1.0
        assert GeoRiskEngine._vix_confidence_modifier(50) == 0.5

    def test_determine_action_flat_low_confidence(self) -> None:
        action = GeoRiskEngine._determine_action(0.5, 0.1, Urgency.MEDIUM)
        assert action == TradeAction.FLAT

    def test_composite_bounds(self) -> None:
        signal = self.engine.compute_signal(
            _make_geo(10, Urgency.CRITICAL),
            _make_tech(1.0),
            _make_sent(1.0),
            vix_level=10.0,
        )
        assert -1.0 <= signal.composite_score <= 1.0
        assert 0.0 <= signal.confidence <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
