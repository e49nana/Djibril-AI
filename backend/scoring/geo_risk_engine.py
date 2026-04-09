"""
Djibril AI — Geopolitical Risk Engine

Orchestrates the three scoring engines (geo 40%, technical 40%, sentiment 20%),
applies VIX adjustment, detects signal conflicts, and produces the final
GeoSignal with confidence and risk flags.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

try:
    from ..utils.config import get_settings
    from ..utils.logger import get_logger, timed
    from ..utils.models import (
        GeoScore,
        GeoSignal,
        RiskFlag,
        SentimentScore,
        TechnicalScore,
        TradeAction,
        Urgency,
    )
except ImportError:
    from utils.config import get_settings
    from utils.logger import get_logger, timed
    from utils.models import (
        GeoScore,
        GeoSignal,
        RiskFlag,
        SentimentScore,
        TechnicalScore,
        TradeAction,
        Urgency,
    )

logger = get_logger(__name__)

# VIX thresholds
_VIX_CALM = 15.0
_VIX_ELEVATED = 25.0
_VIX_EXTREME = 35.0


class GeoRiskEngine:
    """Central risk engine that combines all scoring layers into a unified signal.

    Weighting: geo (40%) + technical (40%) + sentiment (20%)
    VIX acts as a confidence modifier.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    @timed
    def compute_signal(
        self,
        geo_score: GeoScore,
        technical_score: TechnicalScore,
        sentiment_score: SentimentScore,
        vix_level: Optional[float] = None,
    ) -> GeoSignal:
        """Combine all scores into a final GeoSignal.

        Args:
            geo_score: Claude-derived geopolitical score.
            technical_score: WTI technical analysis score.
            sentiment_score: Market sentiment score.
            vix_level: Current VIX value (fetched or passed in).

        Returns:
            GeoSignal with composite score, confidence, and risk flags.
        """
        if vix_level is None:
            vix_level = self._fetch_vix()

        cfg = self._settings.trading
        risk_flags: List[RiskFlag] = []

        # ── Normalize geo score to [-1, +1] ──
        geo_normalized = geo_score.score / 10.0

        # ── Weighted composite ──
        composite = (
            geo_normalized * cfg.geo_weight
            + technical_score.score * cfg.technical_weight
            + sentiment_score.score * cfg.sentiment_weight
        )

        # ── Detect signal conflicts ──
        conflicts = self._detect_conflicts(
            geo_normalized, technical_score.score, sentiment_score.score
        )
        for conflict in conflicts:
            risk_flags.append(conflict)

        # ── VIX adjustment ──
        vix_multiplier = self._vix_confidence_modifier(vix_level)
        if vix_level > _VIX_ELEVATED:
            risk_flags.append(
                RiskFlag(
                    flag_type="high_vix",
                    message=f"VIX at {vix_level:.1f} — elevated volatility reduces confidence.",
                    severity=Urgency.HIGH if vix_level > _VIX_EXTREME else Urgency.MEDIUM,
                )
            )

        # ── Compute confidence ──
        base_confidence = abs(composite)
        # Reduce confidence if signals conflict
        conflict_penalty = len([f for f in risk_flags if f.flag_type == "signal_conflict"]) * 0.15
        confidence = max(0.0, min(1.0, base_confidence * vix_multiplier - conflict_penalty))

        # ── Determine action ──
        action = self._determine_action(composite, confidence, geo_score.urgency)

        # ── Add urgency-based flags ──
        if geo_score.urgency == Urgency.CRITICAL:
            risk_flags.append(
                RiskFlag(
                    flag_type="critical_geo_event",
                    message="Critical geopolitical event detected — heightened risk.",
                    severity=Urgency.CRITICAL,
                )
            )

        # ── Low liquidity check ──
        if technical_score.volume_ratio < 0.5:
            risk_flags.append(
                RiskFlag(
                    flag_type="low_liquidity",
                    message=f"Volume ratio {technical_score.volume_ratio:.2f} — below average.",
                    severity=Urgency.LOW,
                )
            )

        signal = GeoSignal(
            geo_score=geo_score,
            technical_score=technical_score,
            sentiment_score=sentiment_score,
            composite_score=round(max(-1.0, min(1.0, composite)), 4),
            confidence=round(confidence, 4),
            suggested_action=action,
            vix_level=vix_level,
            risk_flags=risk_flags,
            computed_at=datetime.now(timezone.utc),
        )

        logger.info(
            "risk_engine_signal",
            composite=signal.composite_score,
            confidence=signal.confidence,
            action=signal.suggested_action.value,
            risk_flags=len(risk_flags),
            vix=vix_level,
        )
        return signal

    @staticmethod
    def _detect_conflicts(
        geo: float, tech: float, sentiment: float
    ) -> List[RiskFlag]:
        """Detect conflicts between scoring signals.

        Args:
            geo: Normalized geo score [-1, 1].
            tech: Technical score [-1, 1].
            sentiment: Sentiment score [-1, 1].

        Returns:
            List of RiskFlag for detected conflicts.
        """
        flags: List[RiskFlag] = []
        threshold = 0.3

        # Geo bullish but tech bearish (or vice versa)
        if geo > threshold and tech < -threshold:
            flags.append(
                RiskFlag(
                    flag_type="signal_conflict",
                    message=f"Geo bullish ({geo:+.2f}) conflicts with tech bearish ({tech:+.2f}).",
                    severity=Urgency.MEDIUM,
                )
            )
        elif geo < -threshold and tech > threshold:
            flags.append(
                RiskFlag(
                    flag_type="signal_conflict",
                    message=f"Geo bearish ({geo:+.2f}) conflicts with tech bullish ({tech:+.2f}).",
                    severity=Urgency.MEDIUM,
                )
            )

        # Sentiment vs composite direction
        avg_direction = (geo + tech) / 2
        if abs(sentiment) > threshold and (avg_direction * sentiment < 0):
            flags.append(
                RiskFlag(
                    flag_type="signal_conflict",
                    message=f"Sentiment ({sentiment:+.2f}) opposes geo+tech average ({avg_direction:+.2f}).",
                    severity=Urgency.LOW,
                )
            )

        return flags

    @staticmethod
    def _vix_confidence_modifier(vix: float) -> float:
        """Calculate confidence multiplier based on VIX level.

        High VIX = more uncertainty = lower confidence in directional signals.
        Low VIX = calmer markets = higher confidence.

        Args:
            vix: Current VIX value.

        Returns:
            Multiplier between 0.5 and 1.2.
        """
        if vix <= _VIX_CALM:
            return 1.2
        elif vix <= _VIX_ELEVATED:
            return 1.0 - (vix - _VIX_CALM) / (_VIX_ELEVATED - _VIX_CALM) * 0.2
        elif vix <= _VIX_EXTREME:
            return 0.8 - (vix - _VIX_ELEVATED) / (_VIX_EXTREME - _VIX_ELEVATED) * 0.2
        else:
            return 0.5  # Extreme volatility — low confidence

    @staticmethod
    def _determine_action(
        composite: float,
        confidence: float,
        urgency: Urgency,
    ) -> TradeAction:
        """Determine trade action from composite score and confidence.

        Args:
            composite: Weighted composite score [-1, 1].
            confidence: Confidence level [0, 1].
            urgency: Geo urgency level.

        Returns:
            BUY, SELL, or FLAT.
        """
        min_confidence = 0.3

        if confidence < min_confidence:
            return TradeAction.FLAT

        # Higher threshold for non-critical events
        threshold = 0.15 if urgency in (Urgency.HIGH, Urgency.CRITICAL) else 0.25

        if composite > threshold:
            return TradeAction.BUY
        elif composite < -threshold:
            return TradeAction.SELL
        else:
            return TradeAction.FLAT

    @staticmethod
    def _fetch_vix() -> float:
        """Fetch current VIX level from yfinance.

        Returns:
            VIX value, or 20.0 as default if unavailable.
        """
        try:
            import yfinance as yf
            vix = yf.Ticker("^VIX")
            hist = vix.history(period="1d")
            if hist is not None and len(hist) > 0:
                return float(hist["Close"].iloc[-1])
        except Exception as exc:
            logger.debug("vix_fetch_failed", error=str(exc))

        return 20.0  # Default moderate VIX
