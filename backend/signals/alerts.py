"""
Djibril AI — Alerts & Notifications

Sends trade signals via Telegram and Discord with cooldown management,
rich markdown formatting, and emoji indicators.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

import aiohttp

try:
    from ..utils.config import get_settings
    from ..utils.logger import get_logger, timed
    from ..utils.models import TradeAction, TradeSignal, Urgency
except ImportError:
    from utils.config import get_settings
    from utils.logger import get_logger, timed
    from utils.models import TradeAction, TradeSignal, Urgency

logger = get_logger(__name__)

_URGENCY_EMOJI = {
    Urgency.LOW: "🟢",
    Urgency.MEDIUM: "🟡",
    Urgency.HIGH: "🟠",
    Urgency.CRITICAL: "🔴",
}

_ACTION_EMOJI = {
    TradeAction.BUY: "📈 BUY",
    TradeAction.SELL: "📉 SELL",
    TradeAction.FLAT: "⏸️ FLAT",
}


class AlertManager:
    """Multi-channel alert dispatcher with cooldown throttling."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._last_alert_time: dict[str, float] = {}  # key -> timestamp
        self._cooldown = self._settings.telegram.cooldown_seconds

    @timed
    async def send_signal_alert(self, signal: TradeSignal) -> None:
        """Send a trade signal alert to all configured channels.

        Respects cooldown to avoid alert fatigue.

        Args:
            signal: The TradeSignal to broadcast.
        """
        # Skip FLAT signals unless critical urgency
        if signal.action == TradeAction.FLAT and signal.urgency != Urgency.CRITICAL:
            return

        # Cooldown check
        cooldown_key = f"{signal.action.value}_{signal.urgency.value}"
        if self._is_in_cooldown(cooldown_key):
            logger.info("alert_cooldown_active", key=cooldown_key)
            return

        message = self._format_message(signal)

        tasks = []
        if self._settings.telegram.bot_token and self._settings.telegram.chat_id:
            tasks.append(self._send_telegram(message))
        if self._settings.discord.webhook_url:
            tasks.append(self._send_discord(message))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.warning("alert_send_failed", channel=i, error=str(result))

        self._last_alert_time[cooldown_key] = time.time()

    def _is_in_cooldown(self, key: str) -> bool:
        """Check if the given alert type is still in cooldown.

        Args:
            key: Cooldown identifier.

        Returns:
            True if still in cooldown period.
        """
        last = self._last_alert_time.get(key, 0)
        return (time.time() - last) < self._cooldown

    @staticmethod
    def _format_message(signal: TradeSignal) -> str:
        """Format a TradeSignal into a rich markdown alert message.

        Args:
            signal: The signal to format.

        Returns:
            Markdown-formatted string.
        """
        urgency_emoji = _URGENCY_EMOJI.get(signal.urgency, "⚪")
        action_text = _ACTION_EMOJI.get(signal.action, signal.action.value)

        lines = [
            f"🛢️ *Djibril AI Signal* {urgency_emoji}",
            "",
            f"*{action_text}* {signal.symbol}",
            f"━━━━━━━━━━━━━━━",
            f"📊 Entry: `${signal.entry_price:.2f}`",
        ]

        if signal.action != TradeAction.FLAT:
            lines.extend([
                f"🛑 SL: `${signal.stop_loss:.2f}` ({signal.sl_pips:.0f} pips)",
                f"🎯 TP: `${signal.take_profit:.2f}` ({signal.tp_pips:.0f} pips)",
                f"📐 R:R: `{signal.risk_reward_ratio:.2f}`",
                f"📦 Lots: `{signal.lot_size}`",
                f"🔑 Kelly: `{signal.kelly_fraction:.3f}`",
            ])

        lines.extend([
            f"━━━━━━━━━━━━━━━",
            f"📈 Confidence: `{signal.confidence:.0%}`",
            f"🌍 Geo Score: `{signal.geo_score:+d}/10`",
            f"⚡ Urgency: `{signal.urgency.value}`",
            "",
            f"💡 _{signal.reasoning[:300]}_",
        ])

        if signal.risk_flags:
            lines.append("")
            lines.append("⚠️ *Risk Flags:*")
            for flag in signal.risk_flags[:5]:
                lines.append(f"  • {flag}")

        lines.extend([
            "",
            f"🕐 {signal.created_at.strftime('%Y-%m-%d %H:%M UTC')}",
            f"🆔 `{signal.signal_id}`",
        ])

        return "\n".join(lines)

    async def _send_telegram(self, message: str) -> None:
        """Send message via Telegram Bot API.

        Args:
            message: Markdown-formatted message text.
        """
        cfg = self._settings.telegram
        url = f"https://api.telegram.org/bot{cfg.bot_token}/sendMessage"
        payload = {
            "chat_id": cfg.chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning("telegram_send_error", status=resp.status, body=body[:200])
                else:
                    logger.info("telegram_alert_sent")

    async def _send_discord(self, message: str) -> None:
        """Send message via Discord webhook.

        Args:
            message: Message text (Discord uses its own markdown).
        """
        url = self._settings.discord.webhook_url
        if not url:
            return

        # Convert Telegram markdown to Discord-compatible
        discord_msg = message.replace("*", "**").replace("`", "`")
        payload = {"content": discord_msg}

        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status not in (200, 204):
                    logger.warning("discord_send_error", status=resp.status)
                else:
                    logger.info("discord_alert_sent")
