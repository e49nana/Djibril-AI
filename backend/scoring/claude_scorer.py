"""
Djibril AI — Claude Geopolitical Scorer

Uses Claude claude-opus-4-6 via the Anthropic API to analyze news headlines
and produce a structured geopolitical risk score for oil markets.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from ..utils.config import get_settings
    from ..utils.logger import get_logger, timed
    from ..utils.models import GeoScore, NewsItem, Urgency
except ImportError:
    from utils.config import get_settings
    from utils.logger import get_logger, timed
    from utils.models import GeoScore, NewsItem, Urgency

logger = get_logger(__name__)

# ── Scoring prompt template ──
_SYSTEM_PROMPT = """You are an expert geopolitical analyst specializing in Middle East energy security and oil markets. You analyze news headlines to assess geopolitical risk levels that could impact crude oil prices (WTI/Brent).

Your analysis must be precise, data-driven, and focused on supply-side disruption risks.

SCORING RULES:
- Score range: -10 (maximum de-escalation, bearish for oil) to +10 (maximum escalation, bullish for oil)
- Score 0 = neutral, no significant geopolitical impact
- Positive scores = escalation / supply risk / bullish pressure on oil
- Negative scores = de-escalation / supply stability / bearish pressure on oil

URGENCY LEVELS:
- "low": Routine diplomatic activity, minor policy changes
- "medium": Meaningful policy shifts, moderate tensions, sanctions adjustments
- "high": Active military posturing, significant sanctions, supply threats
- "critical": Imminent military conflict, active blockade, direct supply disruption

KEY FACTORS TO WEIGH:
1. Strait of Hormuz / Persian Gulf shipping lane threats (highest weight)
2. Iran nuclear program escalation/de-escalation
3. OPEC+ production decisions related to geopolitics
4. Military actions affecting oil infrastructure
5. Sanctions enforcement changes
6. Houthi/Red Sea shipping disruptions
7. Iran-Saudi/Iran-Israel tensions

RESPOND ONLY WITH VALID JSON — no markdown, no commentary."""

_USER_PROMPT_TEMPLATE = """Analyze the following {count} recent geopolitical headlines and produce a single aggregated risk assessment for crude oil markets.

HEADLINES:
{headlines}

Respond with this exact JSON structure:
{{
    "score": <integer -10 to +10>,
    "urgency": "<low|medium|high|critical>",
    "reasoning": "<2-3 sentence analysis explaining the score>",
    "key_events": ["<event 1>", "<event 2>", ...],
    "oil_impact": "<bullish|bearish|neutral>"
}}"""


class ClaudeScorer:
    """Geopolitical news scorer powered by Claude claude-opus-4-6.

    Receives a batch of NewsItem objects, constructs a structured prompt,
    calls Claude via the Anthropic API, and returns a validated GeoScore.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: Any = None
        self._cache: Dict[str, tuple[GeoScore, float]] = {}
        self._cache_ttl = self._settings.anthropic.scoring_cache_ttl_seconds

    def _get_client(self) -> Any:
        """Lazy-init the Anthropic client.

        Returns:
            Anthropic client instance.

        Raises:
            RuntimeError: If ANTHROPIC_API_KEY is not set.
        """
        if self._client is None:
            api_key = self._settings.anthropic.api_key
            if not api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY not set. Cannot initialize Claude scorer."
                )
            import anthropic
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    @timed
    def score_headlines(
        self,
        items: List[NewsItem],
        use_cache: bool = True,
        force_thinking: bool = False,
    ) -> GeoScore:
        """Score a batch of news headlines for geopolitical oil risk.

        Uses adaptive thinking: first does a quick pass; if urgency is
        critical, re-scores with Claude's extended thinking mode for
        deeper analysis.

        Args:
            items: List of NewsItem to analyze.
            use_cache: Whether to check/use the scoring cache.
            force_thinking: Force extended thinking regardless of urgency.

        Returns:
            GeoScore with the aggregated assessment.
        """
        if not items:
            logger.info("claude_scorer_no_items")
            return GeoScore(
                score=0,
                urgency=Urgency.LOW,
                reasoning="No headlines to analyze.",
                oil_impact="neutral",
                headlines_analyzed=0,
            )

        # Build cache key from sorted title hashes
        cache_key = self._build_cache_key(items)
        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                logger.info("claude_scorer_cache_hit", headlines=len(items))
                return cached

        # Build the prompt
        headlines_text = self._format_headlines(items)
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            count=len(items),
            headlines=headlines_text,
        )

        # First pass: standard scoring
        try:
            raw_response = self._call_claude(user_prompt, use_thinking=force_thinking)
            geo_score = self._parse_response(raw_response, len(items))
        except Exception as exc:
            logger.error("claude_scorer_failed", error=str(exc))
            geo_score = self._fallback_score(items)

        # Adaptive thinking: re-score with deeper analysis if critical
        if geo_score.urgency == Urgency.CRITICAL and not force_thinking:
            logger.info(
                "claude_scorer_critical_rescore",
                initial_score=geo_score.score,
            )
            try:
                enhanced_prompt = (
                    f"{user_prompt}\n\n"
                    "CRITICAL EVENT DETECTED. Provide an extremely detailed analysis.\n"
                    "Consider second-order effects, historical parallels, and "
                    "specific supply disruption quantities (mb/d at risk)."
                )
                raw_response = self._call_claude(enhanced_prompt, use_thinking=True)
                geo_score = self._parse_response(raw_response, len(items))
                logger.info(
                    "claude_scorer_thinking_complete",
                    final_score=geo_score.score,
                )
            except Exception as exc:
                logger.warning("claude_scorer_thinking_failed", error=str(exc))
                # Keep the first-pass score

        # Cache the result
        self._cache[cache_key] = (geo_score, time.time())

        return geo_score

    def _call_claude(
        self,
        user_prompt: str,
        use_thinking: bool = False,
    ) -> str:
        """Make the API call to Claude.

        Args:
            user_prompt: The user message content.
            use_thinking: Whether to enable extended thinking.

        Returns:
            Raw text response from Claude.
        """
        client = self._get_client()
        model = self._settings.anthropic.model

        kwargs: Dict[str, Any] = {
            "model": model,
            "max_tokens": self._settings.anthropic.max_tokens,
            "system": _SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        if use_thinking:
            kwargs["temperature"] = 1  # Required for extended thinking
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": 5000,
            }

        response = client.messages.create(**kwargs)

        # Extract text content
        for block in response.content:
            if hasattr(block, "text"):
                return block.text

        raise ValueError("No text content in Claude response")

    def _call_claude_with_thinking(self, user_prompt: str) -> str:
        """Call Claude with adaptive thinking for critical events.

        Args:
            user_prompt: The user message.

        Returns:
            Raw text response.
        """
        return self._call_claude(user_prompt, use_thinking=True)

    def _parse_response(self, raw: str, headline_count: int) -> GeoScore:
        """Parse and validate the JSON response from Claude.

        Args:
            raw: Raw text from the API.
            headline_count: Number of headlines analyzed.

        Returns:
            Validated GeoScore.
        """
        # Strip any markdown fences
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("claude_scorer_json_parse_error", raw=raw[:200], error=str(exc))
            raise ValueError(f"Failed to parse Claude response as JSON: {exc}")

        # Validate and clamp values
        score = max(-10, min(10, int(data.get("score", 0))))
        urgency_raw = data.get("urgency", "low").lower()
        try:
            urgency = Urgency(urgency_raw)
        except ValueError:
            urgency = Urgency.LOW

        oil_impact = data.get("oil_impact", "neutral").lower()
        if oil_impact not in ("bullish", "bearish", "neutral"):
            oil_impact = "neutral"

        return GeoScore(
            score=score,
            urgency=urgency,
            reasoning=str(data.get("reasoning", ""))[:500],
            key_events=[str(e) for e in data.get("key_events", [])][:10],
            oil_impact=oil_impact,
            scored_at=datetime.now(timezone.utc),
            headlines_analyzed=headline_count,
            model_used=self._settings.anthropic.model,
        )

    @staticmethod
    def _format_headlines(items: List[NewsItem]) -> str:
        """Format NewsItem list into numbered headline text.

        Args:
            items: List of NewsItem.

        Returns:
            Formatted string with numbered headlines.
        """
        lines: list[str] = []
        for i, item in enumerate(items, 1):
            source = item.source_name or "unknown"
            date = item.published_at.strftime("%Y-%m-%d %H:%M UTC")
            line = f"{i}. [{source}] {item.title}"
            if item.description:
                line += f" — {item.description[:150]}"
            line += f" ({date})"
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _build_cache_key(items: List[NewsItem]) -> str:
        """Build a deterministic cache key from headline hashes.

        Args:
            items: NewsItem list.

        Returns:
            SHA-256 hex digest (first 24 chars).
        """
        hashes = sorted(item.title_hash for item in items)
        combined = "|".join(hashes)
        return hashlib.sha256(combined.encode()).hexdigest()[:24]

    def _get_from_cache(self, key: str) -> Optional[GeoScore]:
        """Retrieve a cached GeoScore if not expired.

        Args:
            key: Cache key.

        Returns:
            Cached GeoScore or None.
        """
        if key in self._cache:
            score, cached_at = self._cache[key]
            if (time.time() - cached_at) < self._cache_ttl:
                return score
            else:
                del self._cache[key]
        return None

    @staticmethod
    def _fallback_score(items: List[NewsItem]) -> GeoScore:
        """Produce a simple keyword-based fallback score when Claude is unavailable.

        Args:
            items: NewsItem list.

        Returns:
            Basic GeoScore derived from keyword counting.
        """
        high_tension_kw = [
            "strike", "attack", "blockade", "war", "missile",
            "closure", "military", "escalat",
        ]
        deescalation_kw = [
            "peace", "agreement", "deal", "negotiat", "cooperat",
            "ceasefire", "diplomacy",
        ]

        tension_count = 0
        peace_count = 0
        for item in items:
            text = f"{item.title} {item.description}".lower()
            tension_count += sum(1 for kw in high_tension_kw if kw in text)
            peace_count += sum(1 for kw in deescalation_kw if kw in text)

        raw_score = tension_count - peace_count
        score = max(-10, min(10, raw_score))

        if abs(score) >= 7:
            urgency = Urgency.HIGH
        elif abs(score) >= 4:
            urgency = Urgency.MEDIUM
        else:
            urgency = Urgency.LOW

        return GeoScore(
            score=score,
            urgency=urgency,
            reasoning=f"Fallback scoring: {tension_count} tension keywords, {peace_count} de-escalation keywords.",
            key_events=[],
            oil_impact="bullish" if score > 2 else "bearish" if score < -2 else "neutral",
            headlines_analyzed=len(items),
            model_used="fallback-keyword",
        )
