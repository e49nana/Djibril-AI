"""
Djibril AI — Signal Composer

Takes a GeoSignal, applies trading filters (spread, session, R:R),
calculates SL/TP from ATR, computes lot size via Kelly, and produces
the final executable TradeSignal.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    from ..utils.config import get_settings
    from ..utils.logger import get_logger, timed
    from ..utils.models import GeoSignal, TradeAction, TradeSignal, Urgency
    from .kelly_calculator import KellyCalculator
except ImportError:
    from utils.config import get_settings
    from utils.logger import get_logger, timed
    from utils.models import GeoSignal, TradeAction, TradeSignal, Urgency
    from signals.kelly_calculator import KellyCalculator

logger = get_logger(__name__)


class SignalComposer:
    """Transforms a GeoSignal into an executable TradeSignal.

    Applies all pre-trade filters, computes stop-loss and take-profit
    from ATR, validates risk-reward, and sizes the position via Kelly.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._kelly = KellyCalculator()

    @timed
    def compose(
        self,
        geo_signal: GeoSignal,
        current_spread: float = 0.0,
    ) -> TradeSignal:
        """Compose the final trade signal from a GeoSignal.

        Args:
            geo_signal: Aggregated signal from the risk engine.
            current_spread: Current broker spread in points.

        Returns:
            TradeSignal ready for execution (or FLAT if filters reject).
        """
        cfg = self._settings.trading
        action = geo_signal.suggested_action
        tech = geo_signal.technical_score

        # ── Filter: action must be BUY or SELL ──
        if action == TradeAction.FLAT:
            return self._flat_signal("No actionable signal (FLAT).", geo_signal)

        # ── Filter: minimum confidence ──
        if geo_signal.confidence < cfg.min_confidence:
            return self._flat_signal(
                f"Confidence {geo_signal.confidence:.2f} below minimum {cfg.min_confidence}.",
                geo_signal,
            )

        # ── Filter: spread check ──
        if current_spread > cfg.max_spread_points:
            return self._flat_signal(
                f"Spread {current_spread} exceeds max {cfg.max_spread_points}.",
                geo_signal,
            )

        # ── Filter: session hours ──
        now_utc = datetime.now(timezone.utc)
        if not self._is_in_session(now_utc.hour, cfg.session_start_utc, cfg.session_end_utc):
            return self._flat_signal(
                f"Outside trading session ({cfg.session_start_utc}–{cfg.session_end_utc} UTC).",
                geo_signal,
            )

        # ── Calculate SL/TP from ATR ──
        atr = tech.atr_14
        if atr <= 0:
            atr = 1.50  # Default ATR fallback ($1.50)
            logger.warning("signal_composer_atr_fallback", default_atr=atr)

        price = tech.current_price
        if price <= 0:
            return self._flat_signal("No current price available.", geo_signal)

        sl_distance = atr * cfg.sl_atr_multiplier
        tp_distance = atr * cfg.tp_atr_multiplier

        if action == TradeAction.BUY:
            stop_loss = price - sl_distance
            take_profit = price + tp_distance
        else:  # SELL
            stop_loss = price + sl_distance
            take_profit = price - tp_distance

        # Convert to pips (for WTI, 1 pip = $0.01)
        sl_pips = sl_distance * 100  # $1.50 SL = 150 pips
        tp_pips = tp_distance * 100

        # ── Filter: minimum R:R ──
        rr_ratio = tp_distance / sl_distance if sl_distance > 0 else 0.0
        if rr_ratio < cfg.min_rr_ratio:
            return self._flat_signal(
                f"R:R {rr_ratio:.2f} below minimum {cfg.min_rr_ratio}.",
                geo_signal,
            )

        # ── Kelly position sizing ──
        position = self._kelly.calculate(
            sl_pips=sl_pips,
            confidence=geo_signal.confidence,
        )

        # ── Build final signal ──
        signal_id = f"OG-{now_utc.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        risk_flag_strs = [f.message for f in geo_signal.risk_flags]

        reasoning_parts = [
            f"Action: {action.value}",
            f"Geo: {geo_signal.geo_score.score:+d}/10 ({geo_signal.geo_score.urgency.value})",
            f"Tech: {tech.score:+.2f}",
            f"Sent: {geo_signal.sentiment_score.score:+.2f}",
            f"Composite: {geo_signal.composite_score:+.3f}",
            f"Confidence: {geo_signal.confidence:.2f}",
        ]
        if geo_signal.geo_score.reasoning:
            reasoning_parts.append(f"AI: {geo_signal.geo_score.reasoning[:200]}")

        trade_signal = TradeSignal(
            signal_id=signal_id,
            action=action,
            symbol="XTIUSD",
            confidence=geo_signal.confidence,
            entry_price=round(price, 4),
            stop_loss=round(stop_loss, 4),
            take_profit=round(take_profit, 4),
            lot_size=position.lot_size,
            kelly_fraction=position.half_kelly,
            sl_pips=round(sl_pips, 1),
            tp_pips=round(tp_pips, 1),
            risk_reward_ratio=round(rr_ratio, 2),
            max_spread_allowed=cfg.max_spread_points,
            reasoning=" | ".join(reasoning_parts),
            geo_score=geo_signal.geo_score.score,
            technical_score_value=tech.score,
            sentiment_score_value=geo_signal.sentiment_score.score,
            urgency=geo_signal.geo_score.urgency,
            risk_flags=risk_flag_strs,
            created_at=now_utc,
            expires_at=now_utc + timedelta(seconds=self._settings.signal.timeout_seconds),
        )

        logger.info(
            "signal_composed",
            signal_id=signal_id,
            action=action.value,
            price=price,
            sl=stop_loss,
            tp=take_profit,
            lots=position.lot_size,
            rr=rr_ratio,
        )
        return trade_signal

    @staticmethod
    def _is_in_session(current_hour: int, start: int, end: int) -> bool:
        """Check if current hour is within the trading session.

        Args:
            current_hour: Current UTC hour (0–23).
            start: Session start hour UTC.
            end: Session end hour UTC.

        Returns:
            True if within session.
        """
        if start <= end:
            return start <= current_hour < end
        else:
            # Wraps around midnight
            return current_hour >= start or current_hour < end

    def _flat_signal(self, reason: str, geo_signal: GeoSignal) -> TradeSignal:
        """Create a FLAT (no-trade) signal with reasoning.

        Args:
            reason: Why the signal was rejected.
            geo_signal: The original GeoSignal.

        Returns:
            TradeSignal with action=FLAT.
        """
        logger.info("signal_rejected", reason=reason)
        now = datetime.now(timezone.utc)
        return TradeSignal(
            signal_id=f"OG-FLAT-{now.strftime('%Y%m%d-%H%M%S')}",
            action=TradeAction.FLAT,
            reasoning=reason,
            geo_score=geo_signal.geo_score.score,
            technical_score_value=geo_signal.technical_score.score,
            sentiment_score_value=geo_signal.sentiment_score.score,
            urgency=geo_signal.geo_score.urgency,
            created_at=now,
        )
