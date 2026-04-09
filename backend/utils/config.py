"""
Djibril AI — Centralized Configuration

Loads all settings from environment variables with sensible defaults.
Uses pydantic-settings for validation and type coercion.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings


class AnthropicConfig(BaseSettings):
    """Claude API configuration."""

    api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    model: str = Field(default="claude-opus-4-6", alias="CLAUDE_MODEL")
    max_tokens: int = 4096
    scoring_cache_ttl_seconds: int = 300  # 5 minutes

    model_config = {"env_prefix": "", "extra": "ignore"}


class NewsAPIConfig(BaseSettings):
    """NewsAPI configuration."""

    api_key: str = Field(default="", alias="NEWSAPI_KEY")
    page_size: int = 50
    language: str = "en"
    sort_by: str = "publishedAt"

    model_config = {"env_prefix": "", "extra": "ignore"}


class TelegramConfig(BaseSettings):
    """Telegram bot notifications."""

    bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    cooldown_seconds: int = 1800  # 30 minutes

    model_config = {"env_prefix": "", "extra": "ignore"}


class DiscordConfig(BaseSettings):
    """Discord webhook notifications."""

    webhook_url: str = Field(default="", alias="DISCORD_WEBHOOK_URL")

    model_config = {"env_prefix": "", "extra": "ignore"}


class TwitterConfig(BaseSettings):
    """Twitter/X API v2."""

    bearer_token: str = Field(default="", alias="TWITTER_BEARER_TOKEN")

    model_config = {"env_prefix": "", "extra": "ignore"}


class TradingConfig(BaseSettings):
    """Trading parameters."""

    account_balance: float = Field(default=10000.0, alias="ACCOUNT_BALANCE")
    max_risk_per_trade: float = Field(default=0.05, alias="MAX_RISK_PER_TRADE")
    default_win_rate: float = Field(default=0.55, alias="DEFAULT_WIN_RATE")
    avg_win_loss_ratio: float = Field(default=1.67, alias="AVG_WIN_LOSS_RATIO")
    max_spread_points: int = Field(default=50, alias="MAX_SPREAD_POINTS")
    magic_number: int = Field(default=202503, alias="MAGIC_NUMBER")

    # Session filter (UTC hours)
    session_start_utc: int = 8   # London open
    session_end_utc: int = 20    # NY close

    # Signal thresholds
    min_confidence: float = 0.6
    min_rr_ratio: float = 1.5
    sl_atr_multiplier: float = 1.5
    tp_atr_multiplier: float = 2.5
    trailing_atr_multiplier: float = 0.8

    # Scoring weights
    geo_weight: float = 0.40
    technical_weight: float = 0.40
    sentiment_weight: float = 0.20

    model_config = {"env_prefix": "", "extra": "ignore"}


class ServerConfig(BaseSettings):
    """FastAPI server settings."""

    host: str = Field(default="0.0.0.0", alias="API_HOST")
    port: int = Field(default=8000, alias="API_PORT")
    api_key: str = Field(default="djibril-secret-key-change-me", alias="API_KEY")
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        alias="CORS_ORIGINS",
    )

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = {"env_prefix": "", "extra": "ignore"}


class DatabaseConfig(BaseSettings):
    """Database settings."""

    url: str = Field(default="sqlite:///djibril.db", alias="DATABASE_URL")
    redis_url: str = Field(default="", alias="REDIS_URL")

    model_config = {"env_prefix": "", "extra": "ignore"}


class SignalConfig(BaseSettings):
    """Signal pipeline settings."""

    output_dir: str = Field(default="./mql5/signals", alias="SIGNAL_OUTPUT_DIR")
    timeout_seconds: int = Field(default=300, alias="SIGNAL_TIMEOUT_SECONDS")
    scan_interval_minutes: int = Field(default=2, alias="SCAN_INTERVAL_MINUTES")
    scoring_interval_minutes: int = Field(default=5, alias="SCORING_INTERVAL_MINUTES")
    signal_check_interval_seconds: int = Field(
        default=30, alias="SIGNAL_CHECK_INTERVAL_SECONDS"
    )
    history_max_records: int = 1000

    @property
    def output_path(self) -> Path:
        p = Path(self.output_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    model_config = {"env_prefix": "", "extra": "ignore"}


class LogConfig(BaseSettings):
    """Logging settings."""

    level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_dir: str = Field(default="./logs", alias="LOG_DIR")

    @property
    def log_path(self) -> Path:
        p = Path(self.log_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    model_config = {"env_prefix": "", "extra": "ignore"}


class Settings:
    """Aggregated application settings — singleton access."""

    def __init__(self) -> None:
        self.anthropic = AnthropicConfig()
        self.newsapi = NewsAPIConfig()
        self.telegram = TelegramConfig()
        self.discord = DiscordConfig()
        self.twitter = TwitterConfig()
        self.trading = TradingConfig()
        self.server = ServerConfig()
        self.database = DatabaseConfig()
        self.signal = SignalConfig()
        self.log = LogConfig()

    # RSS feed URLs for geopolitical monitoring
    RSS_FEEDS: dict[str, str] = {
        "aljazeera": "https://www.aljazeera.com/xml/rss/all.xml",
        "reuters_world": "https://feeds.reuters.com/Reuters/worldNews",
        "bbc_world": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "france24_en": "https://www.france24.com/en/rss",
        "ap_topnews": "https://rsshub.app/apnews/topics/apf-topnews",
        "tass_world": "https://tass.com/rss/v2.xml",
    }

    # Keywords for Iran/oil geopolitical filtering
    GEO_KEYWORDS: list[str] = [
        "iran", "tehran", "khamenei", "irgc", "revolutionary guard",
        "strait of hormuz", "hormuz", "persian gulf", "gulf of oman",
        "oil sanctions", "crude oil", "opec", "opec+",
        "tanker", "pipeline", "refinery",
        "nuclear deal", "jcpoa", "enrichment", "uranium",
        "hezbollah", "houthi", "yemen", "red sea",
        "saudi arabia", "aramco", "iraq oil", "libya oil",
        "wti", "brent", "oil price", "energy crisis",
        "military strike", "drone attack", "missile",
        "sanctions", "embargo", "blockade",
    ]

    # WorldMonitor event categories of interest
    WORLDMONITOR_CATEGORIES: list[str] = [
        "military",
        "sanctions",
        "diplomatic",
        "infrastructure",
        "energy",
        "conflict",
    ]


# Module-level singleton
_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the global Settings singleton, creating it on first call."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
