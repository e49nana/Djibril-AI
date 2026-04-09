"""Tests for Step 11 — kelly_calculator.py validation."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from signals.kelly_calculator import KellyCalculator


class TestKellyCalculator:
    def setup_method(self) -> None:
        self.calc = KellyCalculator()

    def test_basic_calculation(self) -> None:
        result = self.calc.calculate(
            sl_pips=150,
            confidence=0.8,
            win_rate=0.55,
            avg_wl_ratio=1.67,
            account_balance=10000,
            max_risk=0.05,
        )
        assert result.kelly_fraction > 0
        assert result.half_kelly > 0
        assert result.risk_amount_usd > 0
        assert result.lot_size > 0
        assert result.risk_percent <= 0.05

    def test_max_risk_cap(self) -> None:
        result = self.calc.calculate(
            sl_pips=50,
            confidence=1.0,
            win_rate=0.70,
            avg_wl_ratio=2.0,
            account_balance=10000,
            max_risk=0.02,
        )
        assert result.risk_percent <= 0.02
        assert result.capped is True

    def test_negative_kelly(self) -> None:
        result = self.calc.calculate(
            sl_pips=100,
            win_rate=0.30,
            avg_wl_ratio=0.5,
            account_balance=10000,
        )
        assert result.lot_size == 0.0
        assert result.kelly_fraction == 0.0

    def test_zero_sl(self) -> None:
        result = self.calc.calculate(sl_pips=0)
        assert result.lot_size == 0.0

    def test_confidence_scaling(self) -> None:
        high = self.calc.calculate(sl_pips=100, confidence=1.0, account_balance=10000)
        low = self.calc.calculate(sl_pips=100, confidence=0.5, account_balance=10000)
        assert high.risk_amount_usd >= low.risk_amount_usd

    def test_lot_type_detection(self) -> None:
        # Small account -> micro lots
        result = self.calc.calculate(
            sl_pips=200,
            confidence=0.5,
            account_balance=500,
            max_risk=0.02,
        )
        assert result.lot_type in ("micro", "mini", "standard")

    def test_large_account_standard_lots(self) -> None:
        result = self.calc.calculate(
            sl_pips=100,
            confidence=1.0,
            win_rate=0.60,
            avg_wl_ratio=2.0,
            account_balance=100000,
            max_risk=0.05,
        )
        assert result.lot_size > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
