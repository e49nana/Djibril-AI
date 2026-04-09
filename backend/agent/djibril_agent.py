"""
Djibril AI — The Agent Brain

DJIBRIL's core intelligence: a ReAct (Reason + Act) agent powered by
Claude claude-opus-4-6 with persistent memory, multi-step reasoning,
and natural language interface.

This is what transforms DJIBRIL from a pipeline into an agent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

try:
    from ..utils.config import get_settings
    from ..utils.logger import get_logger
    from ..utils.models import GeoScore, NewsItem, TradeSignal
    from .memory import get_memory
except ImportError:
    from utils.config import get_settings
    from utils.logger import get_logger
    from utils.models import GeoScore, NewsItem, TradeSignal
    from agent.memory import get_memory

logger = get_logger(__name__)

_SYSTEM_PROMPT = """\
Tu es DJIBRIL, une intelligence artificielle spécialisée dans l'analyse \
géopolitique des marchés pétroliers (WTI/Brent). Tu as été créé par \
ExMachina Trading Systems. Ta devise : "Precision before profit."

Tu as accès à :
- Les dernières actualités géopolitiques Iran/Moyen-Orient en temps réel
- L'historique de tes signaux passés et leurs résultats
- Les données techniques du marché WTI (RSI, ATR, EMA, SuperTrend)
- Ta mémoire des événements géopolitiques et leur impact historique sur le pétrole

Tu raisonnes en plusieurs étapes avant de répondre :
1. Analyse le contexte géopolitique actuel
2. Compare avec des événements historiques similaires dans ta mémoire
3. Intègre les signaux techniques
4. Formule une réponse précise avec ton niveau de confiance

Tu communiques en français ou anglais selon la langue de l'utilisateur.
Tu es direct, précis, et tu quantifies toujours ton incertitude.
Tu n'inventes jamais de données — si tu ne sais pas, tu le dis.
Signe toujours — DJIBRIL."""


class DjibrilAgent:
    """DJIBRIL's reasoning core.

    Wraps an async Anthropic client with persistent memory to answer
    natural-language questions, explain signals, and self-evaluate.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: Any = None
        self._memory = get_memory()

    def _get_client(self) -> Any:
        """Lazy-init the async Anthropic client.

        Returns:
            An ``anthropic.AsyncAnthropic`` instance.

        Raises:
            RuntimeError: When ANTHROPIC_API_KEY is missing.
        """
        if self._client is not None:
            return self._client

        api_key = self._settings.anthropic.api_key
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")

        import anthropic
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        return self._client

    # ── public API ──────────────────────────────────

    async def chat(
        self,
        user_message: str,
        current_signal: Optional[TradeSignal] = None,
        recent_news: Optional[list[NewsItem]] = None,
    ) -> str:
        """Respond to a user message with full contextual awareness.

        Args:
            user_message: Natural language question.
            current_signal: The most recent trade signal, if any.
            recent_news: Recent headlines for context.

        Returns:
            DJIBRIL's response text.
        """
        logger.info("agent_chat_request", message=user_message[:80])

        # Save user message
        await self._memory.add_message("user", user_message)

        # Build context
        history = await self._memory.get_conversation_history(limit=10)
        performance = await self._memory.get_signal_performance()
        recent_events = await self._memory.get_recent_events(limit=10)

        context = self._build_context_message(
            recent_news=recent_news or [],
            current_signal=current_signal,
            history=recent_events,
            performance=performance,
        )

        # Build messages for Claude
        messages: list[dict[str, str]] = []

        # Add conversation history (last 10 turns)
        for msg in history[:-1]:  # exclude the message we just saved
            messages.append({"role": msg["role"], "content": msg["content"]})

        # User message with context prefix
        full_user = f"{context}\n\n---\n\nQuestion de l'utilisateur :\n{user_message}"
        messages.append({"role": "user", "content": full_user})

        response = await self._call_claude(messages, max_tokens=1500, temperature=0.3)

        # Save assistant response
        await self._memory.add_message("assistant", response)

        return response

    async def analyze_signal_decision(
        self,
        signal: TradeSignal,
        news: list[NewsItem],
        geo_score: GeoScore,
    ) -> str:
        """Generate a detailed explanation of a signal decision.

        Args:
            signal: The trade signal to explain.
            news: Headlines that informed the decision.
            geo_score: The geo score at time of signal.

        Returns:
            Markdown explanation (2-4 paragraphs).
        """
        # Find similar historical events
        keywords = []
        for item in news[:5]:
            keywords.extend(item.keywords_matched[:3])
        similar = await self._memory.search_similar_events(list(set(keywords)), limit=3)

        similar_text = ""
        if similar:
            similar_text = "\n\nÉvénements historiques similaires :\n"
            for ev in similar:
                impact = ev.get("impact_on_price")
                impact_str = f"{impact:+.2f}%" if impact is not None else "inconnu"
                similar_text += f"- {ev['title']} (impact prix: {impact_str})\n"

        headlines = "\n".join(
            f"- [{n.category.value}] {n.title}" for n in news[:10]
        )

        prompt = (
            f"Signal émis : {signal.action.value} {signal.symbol}\n"
            f"Confiance : {signal.confidence:.0%}\n"
            f"Prix d'entrée : ${signal.entry_price:.2f}, SL: ${signal.stop_loss:.2f}, "
            f"TP: ${signal.take_profit:.2f}\n"
            f"Score géopolitique : {geo_score.score:+d}/10 ({geo_score.urgency.value})\n"
            f"Raisonnement du scorer : {geo_score.reasoning}\n\n"
            f"Actualités déclencheuses :\n{headlines}"
            f"{similar_text}\n\n"
            "Explique en 2-4 paragraphes pourquoi DJIBRIL a émis ce signal. "
            "Cite les événements clés, compare avec l'historique, "
            "détaille les risques et les objectifs de prix."
        )

        messages = [{"role": "user", "content": prompt}]
        response = await self._call_claude(messages, max_tokens=2000, temperature=0.1)

        await self._memory.add_message(
            "assistant", response, context_signal_id=signal.signal_id
        )
        return response

    async def self_evaluate(self, limit: int = 5) -> str:
        """DJIBRIL evaluates its own recent signal performance.

        Args:
            limit: Number of resolved signals to analyse.

        Returns:
            Markdown narrative of the self-evaluation.
        """
        performance = await self._memory.get_signal_performance()
        recent = await self._memory.get_recent_signals(limit=limit)

        resolved = [s for s in recent if s.get("outcome") is not None]

        if not resolved:
            return (
                "Je n'ai pas encore de signaux résolus à évaluer. "
                "Il faut attendre que mes positions soient clôturées "
                "pour que je puisse analyser ma performance. — DJIBRIL"
            )

        signals_text = ""
        for s in resolved:
            pnl = s.get("pnl_pct")
            pnl_str = f"{pnl:+.2f}%" if pnl is not None else "N/A"
            signals_text += (
                f"- {s['signal_id']}: {s['action']} @ ${s.get('entry_price', 0):.2f} "
                f"→ {s['outcome']} ({pnl_str})\n"
            )

        prompt = (
            f"Voici tes statistiques globales :\n"
            f"Total signaux résolus : {performance['total']}\n"
            f"Wins : {performance['wins']}, Losses : {performance['losses']}\n"
            f"Win rate : {performance['win_rate']:.1%}\n"
            f"P&L moyen : {performance['avg_pnl']:.2f}%\n\n"
            f"Derniers signaux résolus :\n{signals_text}\n"
            "Analyse ta performance : quels signaux étaient corrects et pourquoi ? "
            "Quelles erreurs as-tu commises ? Y a-t-il un pattern dans tes erreurs ? "
            "Que recommandes-tu pour améliorer les paramètres ?"
        )

        messages = [{"role": "user", "content": prompt}]
        response = await self._call_claude(messages, max_tokens=2500, temperature=0.2)

        await self._memory.add_message("assistant", response)
        return response

    async def quick_brief(self) -> str:
        """Generate a 3-5 sentence situational brief.

        Returns:
            Short brief suitable for dashboard header or Telegram.
        """
        recent_events = await self._memory.get_recent_events(limit=5)
        performance = await self._memory.get_signal_performance()
        recent_signals = await self._memory.get_recent_signals(limit=1)

        events_text = ""
        if recent_events:
            events_text = "Événements récents : " + "; ".join(
                e["title"][:60] for e in recent_events[:3]
            )

        last_signal = ""
        if recent_signals:
            s = recent_signals[0]
            last_signal = f"Dernier signal : {s['action']} (confiance {s.get('confidence', 0):.0%})"

        prompt = (
            f"{events_text}\n{last_signal}\n"
            f"Win rate global : {performance['win_rate']:.0%} sur {performance['total']} signaux\n\n"
            "Génère un brief de 3-5 phrases maximum sur la situation actuelle. "
            "Style : concis, factuel, avec emoji pertinents. "
            "Commence par 🛢️."
        )

        messages = [{"role": "user", "content": prompt}]
        response = await self._call_claude(messages, max_tokens=300, temperature=0.3)

        logger.info("agent_brief_generated", length=len(response))
        return response

    # ── internals ───────────────────────────────────

    async def _call_claude(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 1500,
        temperature: float = 0.3,
    ) -> str:
        """Call Claude claude-opus-4-6 via the async Anthropic client.

        Args:
            messages: Conversation messages.
            max_tokens: Response length cap.
            temperature: Sampling temperature.

        Returns:
            Claude's text response.
        """
        try:
            client = self._get_client()
        except RuntimeError:
            return (
                "DJIBRIL offline — clé API Anthropic non configurée. "
                "Configurez ANTHROPIC_API_KEY dans .env pour activer l'agent."
            )

        try:
            response = await client.messages.create(
                model=self._settings.anthropic.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=_SYSTEM_PROMPT,
                messages=messages,
            )
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return "DJIBRIL n'a pas pu formuler de réponse."
        except Exception as exc:
            logger.error("agent_claude_error", error=str(exc))
            return f"DJIBRIL a rencontré une erreur : {str(exc)[:200]}"

    @staticmethod
    def _build_context_message(
        recent_news: list[NewsItem],
        current_signal: Optional[TradeSignal],
        history: list[dict[str, Any]],
        performance: dict[str, Any],
    ) -> str:
        """Build the context block injected before the user question.

        Args:
            recent_news: Latest headlines.
            current_signal: Active trade signal.
            history: Recent geo events from memory.
            performance: Aggregate signal stats.

        Returns:
            Formatted context string.
        """
        parts: list[str] = ["[CONTEXTE DJIBRIL]"]

        # Current signal
        if current_signal and current_signal.action.value != "FLAT":
            parts.append(
                f"Signal actif : {current_signal.action.value} {current_signal.symbol} "
                f"@ ${current_signal.entry_price:.2f} | "
                f"Confiance {current_signal.confidence:.0%} | "
                f"Geo {current_signal.geo_score:+d}"
            )
        else:
            parts.append("Signal actif : FLAT (aucune position)")

        # Performance
        if performance.get("total", 0) > 0:
            parts.append(
                f"Performance : {performance['wins']}W/{performance['losses']}L "
                f"(WR {performance['win_rate']:.0%}, "
                f"avg PnL {performance['avg_pnl']:+.2f}%)"
            )

        # Recent news
        if recent_news:
            headlines = "; ".join(n.title[:50] for n in recent_news[:5])
            parts.append(f"Actualités récentes : {headlines}")

        # Memory events
        if history:
            mem = "; ".join(
                f"{e.get('title', '')[:40]} (score {e.get('score', '?')})"
                for e in history[:3]
            )
            parts.append(f"Mémoire : {mem}")

        return "\n".join(parts)


# ── Singleton ───────────────────────────────────────

_agent_instance: Optional[DjibrilAgent] = None


def get_agent() -> DjibrilAgent:
    """Return the global DjibrilAgent singleton."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = DjibrilAgent()
    return _agent_instance
