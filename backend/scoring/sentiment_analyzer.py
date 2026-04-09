"""
Djibril AI — Market Sentiment Analyzer

Aggregates sentiment from social media and search trends.
Sources: Twitter API v2 (or fallback), StockTwits, Google Trends proxies.
Produces a normalized sentiment score between -1.0 and +1.0.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp

try:
    from ..utils.config import get_settings
    from ..utils.logger import get_logger, timed
    from ..utils.models import SentimentScore
except ImportError:
    from utils.config import get_settings
    from utils.logger import get_logger, timed
    from utils.models import SentimentScore

logger = get_logger(__name__)

# Simple word-level sentiment lexicon for oil market context
_BULLISH_WORDS = [
    "surge", "soar", "rally", "spike", "jump", "rise", "bullish", "up",
    "higher", "gain", "shortage", "disruption", "supply risk", "crisis",
    "blockade", "escalation", "threat", "war", "attack", "tension",
]
_BEARISH_WORDS = [
    "drop", "fall", "plunge", "crash", "decline", "bearish", "down",
    "lower", "oversupply", "glut", "peace", "deal", "agreement",
    "de-escalation", "production increase", "surplus", "recession",
    "demand weak", "slowdown",
]

# StockTwits API
_STOCKTWITS_URL = "https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"

# Twitter search (v2)
_TWITTER_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"


class SentimentAnalyzer:
    """Multi-source market sentiment analyzer for oil trading.

    Combines signals from Twitter, StockTwits, and keyword-based
    analysis to produce a normalized sentiment score.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    @timed
    async def analyze(self) -> SentimentScore:
        """Run all sentiment sources and produce an aggregated score.

        Returns:
            SentimentScore with normalized values.
        """
        timeout = aiohttp.ClientTimeout(total=20)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = {
                "twitter": self._fetch_twitter_sentiment(session),
                "stocktwits": self._fetch_stocktwits_sentiment(session),
                "trends": self._estimate_google_trends(session),
            }
            results: Dict[str, float] = {}
            sample_sizes: Dict[str, int] = {}

            for name, coro in tasks.items():
                try:
                    score, count = await coro
                    results[name] = score
                    sample_sizes[name] = count
                except Exception as exc:
                    logger.warning(f"sentiment_{name}_failed", error=str(exc))
                    results[name] = 0.0
                    sample_sizes[name] = 0

        # Weighted aggregation: Twitter 40%, StockTwits 30%, Trends 30%
        weights = {"twitter": 0.4, "stocktwits": 0.3, "trends": 0.3}
        active_weight = sum(
            weights[k] for k in results if sample_sizes.get(k, 0) > 0
        )

        if active_weight > 0:
            composite = sum(
                results[k] * weights[k]
                for k in results
                if sample_sizes.get(k, 0) > 0
            ) / active_weight
        else:
            composite = 0.0

        total_samples = sum(sample_sizes.values())
        composite = max(-1.0, min(1.0, composite))

        sentiment = SentimentScore(
            score=round(composite, 4),
            twitter_sentiment=round(results.get("twitter", 0.0), 4),
            google_trends_score=round(results.get("trends", 0.0), 4),
            stocktwits_sentiment=round(results.get("stocktwits", 0.0), 4),
            sample_size=total_samples,
            computed_at=datetime.now(timezone.utc),
        )

        logger.info(
            "sentiment_analysis_complete",
            composite=sentiment.score,
            sample_size=total_samples,
            sources_active=sum(1 for v in sample_sizes.values() if v > 0),
        )
        return sentiment

    async def _fetch_twitter_sentiment(
        self, session: aiohttp.ClientSession
    ) -> tuple[float, int]:
        """Fetch and analyze recent oil-related tweets.

        Args:
            session: aiohttp session.

        Returns:
            Tuple of (sentiment_score, sample_count).
        """
        bearer = self._settings.twitter.bearer_token
        if not bearer:
            logger.debug("twitter_no_token")
            return 0.0, 0

        headers = {"Authorization": f"Bearer {bearer}"}
        params = {
            "query": "(#WTI OR #CrudeOil OR #OilTrading OR #Brent) lang:en -is:retweet",
            "max_results": 50,
            "tweet.fields": "text,created_at",
        }

        try:
            async with session.get(
                _TWITTER_SEARCH_URL, headers=headers, params=params
            ) as resp:
                if resp.status != 200:
                    logger.warning("twitter_api_error", status=resp.status)
                    return 0.0, 0
                data = await resp.json()
        except Exception as exc:
            logger.warning("twitter_fetch_error", error=str(exc))
            return 0.0, 0

        tweets = data.get("data", [])
        if not tweets:
            return 0.0, 0

        scores = [self._score_text(t.get("text", "")) for t in tweets]
        avg = sum(scores) / len(scores) if scores else 0.0
        return avg, len(scores)

    async def _fetch_stocktwits_sentiment(
        self, session: aiohttp.ClientSession
    ) -> tuple[float, int]:
        """Fetch sentiment from StockTwits for oil symbols.

        Args:
            session: aiohttp session.

        Returns:
            Tuple of (sentiment_score, sample_count).
        """
        symbols = ["USO", "CL_F", "XLE"]
        all_scores: List[float] = []

        for symbol in symbols:
            try:
                url = _STOCKTWITS_URL.format(symbol=symbol)
                async with session.get(url) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()

                messages = data.get("messages", [])
                for msg in messages:
                    sentiment = msg.get("entities", {}).get("sentiment", {})
                    basic = sentiment.get("basic", "")
                    if basic == "Bullish":
                        all_scores.append(0.5)
                    elif basic == "Bearish":
                        all_scores.append(-0.5)
                    else:
                        # Use keyword scoring as fallback
                        text = msg.get("body", "")
                        all_scores.append(self._score_text(text))
            except Exception as exc:
                logger.debug("stocktwits_symbol_error", symbol=symbol, error=str(exc))
                continue

        if not all_scores:
            return 0.0, 0

        avg = sum(all_scores) / len(all_scores)
        return avg, len(all_scores)

    async def _estimate_google_trends(
        self, session: aiohttp.ClientSession
    ) -> tuple[float, int]:
        """Estimate search interest for oil-crisis-related terms.

        Uses SerpAPI or a simple proxy. Falls back to a neutral score.
        The idea: high search volume for "Iran oil" or "Strait of Hormuz"
        correlates with fear/tension = bullish for oil.

        Args:
            session: aiohttp session.

        Returns:
            Tuple of (score, sample_count).
        """
        # Try Google Trends via a public proxy/API
        # If unavailable, return neutral
        try:
            url = "https://trends.google.com/trends/api/dailytrends"
            params = {"hl": "en-US", "geo": "US", "ns": 15}
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return 0.0, 0
                text = await resp.text()

            # Check if oil/Iran related terms are trending
            text_lower = text.lower()
            crisis_keywords = [
                "iran", "oil", "crude", "hormuz", "opec",
                "energy crisis", "oil price", "gas price",
            ]
            match_count = sum(1 for kw in crisis_keywords if kw in text_lower)

            # More matches = higher tension sentiment (bullish for oil)
            if match_count >= 3:
                return 0.6, match_count
            elif match_count >= 1:
                return 0.3, match_count
            else:
                return 0.0, 0

        except Exception as exc:
            logger.debug("google_trends_error", error=str(exc))
            return 0.0, 0

    @staticmethod
    def _score_text(text: str) -> float:
        """Simple keyword-based sentiment scoring for a text snippet.

        Args:
            text: Raw text to analyze.

        Returns:
            Score between -1.0 (bearish) and +1.0 (bullish for oil).
        """
        text_lower = text.lower()
        bullish = sum(1 for w in _BULLISH_WORDS if w in text_lower)
        bearish = sum(1 for w in _BEARISH_WORDS if w in text_lower)

        total = bullish + bearish
        if total == 0:
            return 0.0

        # Normalized: positive = bullish for oil
        return max(-1.0, min(1.0, (bullish - bearish) / total))
