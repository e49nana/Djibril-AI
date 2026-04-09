"""
Djibril AI — Pydantic Data Models

Defines every data structure flowing through the system:
NewsItem, GeoScore, TechnicalScore, SentimentScore, GeoSignal, TradeSignal, RiskParams.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, computed_field


# ═══════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════

class Urgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TradeAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    FLAT = "FLAT"


class NewsCategory(str, Enum):
    MILITARY = "military"
    SANCTIONS = "sanctions"
    DIPLOMATIC = "diplomatic"
    INFRASTRUCTURE = "infrastructure"
    ENERGY = "energy"
    CONFLICT = "conflict"
    MARKET = "market"
    OTHER = "other"


class SignalSource(str, Enum):
    RSS = "rss"
    NEWSAPI = "newsapi"
    WORLDMONITOR = "worldmonitor"
    TWITTER = "twitter"
    MANUAL = "manual"


# ═══════════════════════════════════════════════════
# News & Data Collection
# ═══════════════════════════════════════════════════

class NewsItem(BaseModel):
    """A single news article or event from any source."""

    title: str
    description: str = ""
    url: str = ""
    source_name: str = ""
    source_type: SignalSource = SignalSource.RSS
    category: NewsCategory = NewsCategory.OTHER
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    keywords_matched: List[str] = Field(default_factory=list)
    relevance_score: float = 0.0  # 0.0–1.0

    @computed_field
    @property
    def title_hash(self) -> str:
        """SHA-256 hash of the title for deduplication."""
        return hashlib.sha256(self.title.lower().strip().encode()).hexdigest()[:16]

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


# ═══════════════════════════════════════════════════
# Scoring Layer
# ═══════════════════════════════════════════════════

class GeoScore(BaseModel):
    """Output of the Claude-powered geopolitical scorer."""

    score: int = Field(ge=-10, le=10, description="Geopolitical tension score: -10 (de-escalation) to +10 (maximum tension)")
    urgency: Urgency = Urgency.LOW
    reasoning: str = ""
    key_events: List[str] = Field(default_factory=list)
    oil_impact: str = ""  # "bullish" / "bearish" / "neutral"
    scored_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    headlines_analyzed: int = 0
    model_used: str = "claude-opus-4-6"


class TechnicalScore(BaseModel):
    """Output of the technical analysis module."""

    score: float = Field(ge=-1.0, le=1.0, description="Technical score: -1 (strong bearish) to +1 (strong bullish)")
    rsi_14: float = 0.0
    atr_14: float = 0.0  # In USD/barrel
    ema_20: float = 0.0
    ema_50: float = 0.0
    supertrend_direction: str = "neutral"  # "bullish" / "bearish" / "neutral"
    volume_ratio: float = 1.0  # Current vs 20-period average
    current_price: float = 0.0
    symbol: str = "CL=F"  # WTI futures
    timeframe: str = "4H"
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SentimentScore(BaseModel):
    """Output of the market sentiment analyzer."""

    score: float = Field(ge=-1.0, le=1.0, description="Sentiment: -1 (bearish) to +1 (bullish)")
    twitter_sentiment: float = 0.0
    google_trends_score: float = 0.0
    stocktwits_sentiment: float = 0.0
    sample_size: int = 0
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ═══════════════════════════════════════════════════
# Aggregated Signal
# ═══════════════════════════════════════════════════

class RiskFlag(BaseModel):
    """A single risk warning."""

    flag_type: str  # "signal_conflict", "high_vix", "low_liquidity", etc.
    message: str
    severity: Urgency = Urgency.MEDIUM


class GeoSignal(BaseModel):
    """Aggregated signal from all scoring engines before trade parameters."""

    geo_score: GeoScore
    technical_score: TechnicalScore
    sentiment_score: SentimentScore
    composite_score: float = Field(ge=-1.0, le=1.0, description="Weighted composite")
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_action: TradeAction = TradeAction.FLAT
    vix_level: float = 0.0
    risk_flags: List[RiskFlag] = Field(default_factory=list)
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ═══════════════════════════════════════════════════
# Trade Signal (Final Output)
# ═══════════════════════════════════════════════════

class TradeSignal(BaseModel):
    """Final executable trade signal sent to the MQL5 EA and dashboard."""

    signal_id: str = ""
    action: TradeAction = TradeAction.FLAT
    symbol: str = "XTIUSD"  # WTI crude (broker-dependent symbol)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    # Execution parameters
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    lot_size: float = 0.01
    kelly_fraction: float = 0.0

    # Risk metrics
    sl_pips: float = 0.0
    tp_pips: float = 0.0
    risk_reward_ratio: float = 0.0
    max_spread_allowed: int = 50

    # Reasoning
    reasoning: str = ""
    geo_score: int = 0
    technical_score_value: float = 0.0
    sentiment_score_value: float = 0.0
    urgency: Urgency = Urgency.LOW
    risk_flags: List[str] = Field(default_factory=list)

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    source: str = "djibril-ai"
    version: str = "1.0.0"

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


# ═══════════════════════════════════════════════════
# WebSocket Message Types
# ═══════════════════════════════════════════════════

class WSMessageType(str, Enum):
    SIGNAL = "signal"
    GEO_SCORE = "geo_score"
    NEWS = "news"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    AGENT_BRIEF = "agent_brief"


class WSMessage(BaseModel):
    """Typed WebSocket message envelope."""

    type: WSMessageType
    payload: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}
