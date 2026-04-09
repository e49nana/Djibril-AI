"""Tests for Step 9 — technical_analyzer.py validation."""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scoring.technical_analyzer import TechnicalAnalyzer


class TestTechnicalAnalyzer:
    def setup_method(self) -> None:
        self.ta = TechnicalAnalyzer()

    def test_compute_rsi_trending_up(self) -> None:
        close = np.array([50 + i * 0.5 for i in range(30)], dtype=float)
        rsi = self.ta._compute_rsi(close)
        assert rsi > 70  # Strong uptrend

    def test_compute_rsi_trending_down(self) -> None:
        close = np.array([80 - i * 0.5 for i in range(30)], dtype=float)
        rsi = self.ta._compute_rsi(close)
        assert rsi < 30  # Strong downtrend

    def test_compute_rsi_insufficient_data(self) -> None:
        close = np.array([50.0, 51.0, 52.0])
        rsi = self.ta._compute_rsi(close)
        assert rsi == 50.0

    def test_compute_atr(self) -> None:
        np.random.seed(42)
        n = 50
        close = 70 + np.cumsum(np.random.randn(n) * 0.5)
        high = close + np.random.rand(n) * 1.5
        low = close - np.random.rand(n) * 1.5
        atr = self.ta._compute_atr(high, low, close)
        assert atr > 0

    def test_compute_ema(self) -> None:
        close = np.array([50 + i * 0.1 for i in range(30)], dtype=float)
        ema20 = self.ta._compute_ema(close, period=20)
        assert ema20 > 50  # EMA should be above starting price

    def test_compute_supertrend_bullish(self) -> None:
        n = 50
        close = np.array([50 + i * 0.3 for i in range(n)], dtype=float)
        high = close + 0.5
        low = close - 0.5
        atr = 1.0
        direction = self.ta._compute_supertrend(high, low, close, atr)
        assert direction == "bullish"

    def test_compute_supertrend_bearish(self) -> None:
        n = 50
        close = np.array([80 - i * 0.3 for i in range(n)], dtype=float)
        high = close + 0.5
        low = close - 0.5
        atr = 1.0
        direction = self.ta._compute_supertrend(high, low, close, atr)
        assert direction == "bearish"

    def test_compute_volume_ratio(self) -> None:
        volume = np.array([1000] * 20 + [2000], dtype=float)
        ratio = self.ta._compute_volume_ratio(volume)
        assert abs(ratio - 2.0) < 0.01

    def test_compute_score_bullish(self) -> None:
        score = self.ta._compute_score(
            rsi=55, ema_20=72, ema_50=70,
            supertrend_dir="bullish", vol_ratio=1.5,
            current_price=75,
        )
        assert score > 0

    def test_compute_score_bearish(self) -> None:
        score = self.ta._compute_score(
            rsi=45, ema_20=68, ema_50=70,
            supertrend_dir="bearish", vol_ratio=1.2,
            current_price=65,
        )
        assert score < 0

    def test_compute_score_bounds(self) -> None:
        score = self.ta._compute_score(
            rsi=90, ema_20=100, ema_50=100,
            supertrend_dir="bearish", vol_ratio=3.0,
            current_price=50,
        )
        assert -1.0 <= score <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
