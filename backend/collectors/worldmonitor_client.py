"""
Djibril AI — WorldMonitor Client

Connects to WorldMonitor.app to extract geopolitical events.
Uses the public API if available, falls back to web scraping.
Filters events on Iran/Gulf/OPEC categories and normalizes to NewsItem.
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
    from ..utils.models import NewsCategory, NewsItem, SignalSource
except ImportError:
    from utils.config import get_settings
    from utils.logger import get_logger, timed
    from utils.models import NewsCategory, NewsItem, SignalSource

logger = get_logger(__name__)

# WorldMonitor API base (public endpoint)
_WM_BASE_URL = "https://worldmonitor.app"
_WM_API_URL = f"{_WM_BASE_URL}/api/v1"

# Category mapping from WorldMonitor labels to our categories
_WM_CATEGORY_MAP: dict[str, NewsCategory] = {
    "military": NewsCategory.MILITARY,
    "armed_conflict": NewsCategory.CONFLICT,
    "sanctions": NewsCategory.SANCTIONS,
    "diplomatic": NewsCategory.DIPLOMATIC,
    "infrastructure": NewsCategory.INFRASTRUCTURE,
    "energy": NewsCategory.ENERGY,
    "terrorism": NewsCategory.CONFLICT,
    "nuclear": NewsCategory.MILITARY,
    "trade": NewsCategory.SANCTIONS,
}

# Region keywords for filtering
_REGION_KEYWORDS: list[str] = [
    "iran", "iraq", "saudi", "yemen", "houthi", "hezbollah",
    "strait of hormuz", "hormuz", "persian gulf", "gulf of oman",
    "red sea", "opec", "aramco", "tehran", "irgc",
    "syria", "lebanon", "qatar", "uae", "bahrain", "kuwait",
    "oil", "crude", "brent", "wti", "petroleum",
]


class WorldMonitorClient:
    """Client for WorldMonitor.app geopolitical event feeds.

    Attempts the public API first, falls back to scraping the event page
    if the API is unavailable.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._session: Optional[aiohttp.ClientSession] = None
        self._api_available: Optional[bool] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return or create an aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    "User-Agent": "DjibrilAI/1.0 (geopolitical-research)",
                    "Accept": "application/json, text/html",
                },
            )
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    @timed
    async def fetch_events(self, limit: int = 50) -> List[NewsItem]:
        """Fetch geopolitical events from WorldMonitor.

        Tries the API first; if unavailable, falls back to page scraping.
        Results are filtered for Iran/Gulf/OPEC relevance.

        Args:
            limit: Maximum number of events to return.

        Returns:
            List of filtered, normalized NewsItem objects.
        """
        try:
            events = await self._fetch_via_api(limit)
            if events:
                self._api_available = True
                return events
        except Exception as exc:
            logger.info("worldmonitor_api_unavailable", error=str(exc))
            self._api_available = False

        # Fallback: scrape the public page
        try:
            events = await self._fetch_via_scrape(limit)
            return events
        except Exception as exc:
            logger.warning("worldmonitor_scrape_failed", error=str(exc))
            return []

    async def _fetch_via_api(self, limit: int) -> List[NewsItem]:
        """Attempt to fetch events via the WorldMonitor REST API.

        Args:
            limit: Max events.

        Returns:
            Parsed and filtered NewsItem list.
        """
        session = await self._get_session()
        url = f"{_WM_API_URL}/events"
        params = {
            "limit": min(limit, 100),
            "sort": "-date",
            "regions": "middle_east,north_africa",
        }

        async with session.get(url, params=params) as resp:
            if resp.status == 404:
                raise ConnectionError("API endpoint not found")
            if resp.status != 200:
                raise ConnectionError(f"API returned status {resp.status}")

            data = await resp.json()

        events: List[Dict[str, Any]] = data.get("events", data.get("data", []))
        if not isinstance(events, list):
            raise ValueError("Unexpected API response format")

        return self._normalize_api_events(events)

    async def _fetch_via_scrape(self, limit: int) -> List[NewsItem]:
        """Fallback: scrape the public WorldMonitor events page.

        Args:
            limit: Max events.

        Returns:
            Parsed and filtered NewsItem list.
        """
        session = await self._get_session()

        # Try the events/feed page
        for path in ["/events", "/feed", "/api/events", "/"]:
            try:
                async with session.get(f"{_WM_BASE_URL}{path}") as resp:
                    if resp.status != 200:
                        continue
                    content_type = resp.headers.get("content-type", "")
                    text = await resp.text()

                    if "json" in content_type:
                        return self._parse_json_response(text, limit)
                    else:
                        return self._parse_html_response(text, limit)
            except Exception:
                continue

        logger.warning("worldmonitor_no_endpoint_worked")
        return []

    def _normalize_api_events(self, events: List[Dict[str, Any]]) -> List[NewsItem]:
        """Convert API event dicts to NewsItem, filtering for relevance.

        Args:
            events: Raw event dicts from the API.

        Returns:
            Filtered NewsItem list.
        """
        items: List[NewsItem] = []
        for ev in events:
            title = ev.get("title", ev.get("headline", "")).strip()
            if not title:
                continue

            description = ev.get("description", ev.get("summary", "")).strip()
            category_raw = ev.get("category", ev.get("type", "other")).lower()
            category = _WM_CATEGORY_MAP.get(category_raw, NewsCategory.OTHER)

            # Date parsing
            date_str = ev.get("date", ev.get("timestamp", ""))
            try:
                pub_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pub_dt = datetime.now(timezone.utc)

            item = NewsItem(
                title=title,
                description=description[:500],
                url=ev.get("url", ev.get("link", "")),
                source_name="worldmonitor",
                source_type=SignalSource.WORLDMONITOR,
                category=category,
                published_at=pub_dt,
                fetched_at=datetime.now(timezone.utc),
            )

            # Filter for regional relevance
            if self._is_relevant(item):
                item.keywords_matched = self._extract_keywords(item)
                item.relevance_score = min(len(item.keywords_matched) / 5.0, 1.0)
                items.append(item)

        logger.info("worldmonitor_events_normalized", total=len(items))
        return items

    def _parse_json_response(self, text: str, limit: int) -> List[NewsItem]:
        """Parse a JSON response body into NewsItems.

        Args:
            text: Raw JSON text.
            limit: Max items to return.

        Returns:
            Filtered NewsItem list.
        """
        import json
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []

        events = data if isinstance(data, list) else data.get("events", data.get("data", []))
        if not isinstance(events, list):
            return []

        return self._normalize_api_events(events[:limit])

    def _parse_html_response(self, html: str, limit: int) -> List[NewsItem]:
        """Extract event-like content from HTML page.

        Uses regex to find headline patterns in the page source.
        This is a best-effort fallback.

        Args:
            html: Raw HTML text.
            limit: Max items.

        Returns:
            Filtered NewsItem list.
        """
        items: List[NewsItem] = []

        # Look for common patterns: <h2>headline</h2>, <article>, data-title, etc.
        patterns = [
            r'<h[23][^>]*>([^<]{20,200})</h[23]>',
            r'data-title="([^"]{20,200})"',
            r'"title"\s*:\s*"([^"]{20,200})"',
            r'"headline"\s*:\s*"([^"]{20,200})"',
        ]

        seen: set[str] = set()
        for pattern in patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches:
                title = match.strip()
                if title in seen or len(title) < 20:
                    continue
                seen.add(title)

                item = NewsItem(
                    title=title,
                    source_name="worldmonitor",
                    source_type=SignalSource.WORLDMONITOR,
                    fetched_at=datetime.now(timezone.utc),
                )

                if self._is_relevant(item):
                    item.keywords_matched = self._extract_keywords(item)
                    item.relevance_score = min(len(item.keywords_matched) / 5.0, 1.0)
                    items.append(item)

                if len(items) >= limit:
                    break

        logger.info("worldmonitor_html_parsed", events_found=len(items))
        return items

    @staticmethod
    def _is_relevant(item: NewsItem) -> bool:
        """Check if a news item matches regional/topical keywords.

        Args:
            item: The NewsItem to check.

        Returns:
            True if any keyword matches title or description.
        """
        text = f"{item.title} {item.description}".lower()
        return any(kw in text for kw in _REGION_KEYWORDS)

    @staticmethod
    def _extract_keywords(item: NewsItem) -> list[str]:
        """Extract matching keywords from a NewsItem.

        Args:
            item: The NewsItem.

        Returns:
            List of matched keyword strings.
        """
        text = f"{item.title} {item.description}".lower()
        return [kw for kw in _REGION_KEYWORDS if kw in text]


# ═══════════════════════════════════════════════════
# WebSocket Persistent Client
# ═══════════════════════════════════════════════════

_WS_ENDPOINTS: list[str] = [
    "wss://worldmonitor.app/ws",
    "wss://worldmonitor.app/ws/events",
    "wss://worldmonitor.app/api/ws",
    "wss://worldmonitor.app/feed/live",
]

_MAX_BACKOFF = 60.0
_CONNECT_TIMEOUT = 15
_FULL_CYCLE_RETRY_WAIT = 300  # 5 minutes


class WorldMonitorWSClient:
    """Persistent WebSocket connection to WorldMonitor.app.

    Pushes geopolitical events into an asyncio.Queue as NewsItem objects
    the instant they arrive. Reconnects automatically with exponential
    backoff (1 s → 2 s → 4 s → … → 60 s max). Falls back silently if
    no WS endpoint is reachable.

    Attributes:
        is_connected: Whether the WS connection is currently open.
        reconnect_count: Total number of reconnection attempts since start.
        last_event_at: Timestamp of the most recent event received.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[NewsItem] = asyncio.Queue(maxsize=500)
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._stop_event = asyncio.Event()

        self.is_connected: bool = False
        self.reconnect_count: int = 0
        self.last_event_at: Optional[datetime] = None

    # ── public API ──────────────────────────────────

    async def run(self) -> None:
        """Main loop: connect → listen → reconnect on failure.

        Runs until stop() is called. Safe to launch as an asyncio task.
        """
        backoff = 1.0
        full_cycle_failures = 0

        while not self._stop_event.is_set():
            connected = await self._try_connect()

            if connected:
                backoff = 1.0
                full_cycle_failures = 0
                await self._listen()
                # _listen exits when WS drops; loop will reconnect
                self.is_connected = False
                continue

            # None of the endpoints worked in this attempt
            self.reconnect_count += 1
            full_cycle_failures += 1

            if full_cycle_failures >= 3:
                logger.warning(
                    "worldmonitor_ws_unavailable",
                    cycles_failed=full_cycle_failures,
                    wait_seconds=_FULL_CYCLE_RETRY_WAIT,
                )
                await self._interruptible_sleep(_FULL_CYCLE_RETRY_WAIT)
                full_cycle_failures = 0
                backoff = 1.0
            else:
                logger.info(
                    "worldmonitor_ws_reconnect",
                    retry=self.reconnect_count,
                    backoff_s=backoff,
                )
                await self._interruptible_sleep(backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF)

    async def stop(self) -> None:
        """Gracefully close the connection and exit the run loop."""
        self._stop_event.set()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        self.is_connected = False
        logger.info("worldmonitor_ws_stopped")

    # ── internals ───────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=_CONNECT_TIMEOUT),
                headers={
                    "User-Agent": "DjibrilAI/1.0 (geopolitical-ws)",
                },
            )
        return self._session

    async def _try_connect(self) -> bool:
        """Try each WS endpoint in order. Return True on first success."""
        session = await self._get_session()

        for endpoint in _WS_ENDPOINTS:
            if self._stop_event.is_set():
                return False
            try:
                self._ws = await session.ws_connect(
                    endpoint,
                    timeout=_CONNECT_TIMEOUT,
                    heartbeat=30,
                )
                self.is_connected = True
                logger.info("worldmonitor_ws_connected", endpoint=endpoint)
                return True
            except Exception as exc:
                logger.debug(
                    "worldmonitor_ws_endpoint_failed",
                    endpoint=endpoint,
                    error=str(exc),
                )
                continue

        return False

    async def _listen(self) -> None:
        """Read messages from the open WS until it closes or errors."""
        if self._ws is None:
            return

        try:
            async for msg in self._ws:
                if self._stop_event.is_set():
                    break

                if msg.type == aiohttp.WSMsgType.TEXT:
                    self._handle_text(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.warning(
                        "worldmonitor_ws_error",
                        error=str(self._ws.exception()),
                    )
                    break
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.CLOSED,
                ):
                    break
        except Exception as exc:
            logger.warning("worldmonitor_ws_listen_error", error=str(exc))

        self.is_connected = False
        logger.info("worldmonitor_ws_disconnected")

    def _handle_text(self, raw: str) -> None:
        """Parse a raw text frame and push relevant events to the queue."""
        import json

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return

        # WorldMonitor may send a single event dict or a list
        events: list[dict[str, Any]] = []
        if isinstance(data, list):
            events = data
        elif isinstance(data, dict):
            # Could be wrapped: {"event": {...}} or {"data": [...]}
            if "event" in data:
                events = [data["event"]]
            elif "data" in data and isinstance(data["data"], list):
                events = data["data"]
            else:
                events = [data]

        for ev in events:
            item = self._parse_ws_event(ev)
            if item is not None:
                try:
                    self._queue.put_nowait(item)
                    self.last_event_at = datetime.now(timezone.utc)
                    logger.info(
                        "worldmonitor_ws_event",
                        title=item.title[:80],
                        category=item.category.value,
                    )
                except asyncio.QueueFull:
                    logger.warning("worldmonitor_ws_queue_full")

    def _parse_ws_event(self, ev: dict[str, Any]) -> Optional[NewsItem]:
        """Convert a raw WS event dict into a NewsItem if relevant.

        Args:
            ev: Raw event dictionary from the WS frame.

        Returns:
            A NewsItem if the event passes relevance filtering, else None.
        """
        title = (ev.get("title") or ev.get("headline") or "").strip()
        if not title or len(title) < 10:
            return None

        description = (ev.get("description") or ev.get("summary") or "").strip()
        category_raw = (ev.get("category") or ev.get("type") or "other").lower()
        category = _WM_CATEGORY_MAP.get(category_raw, NewsCategory.OTHER)

        date_str = ev.get("date") or ev.get("timestamp") or ""
        try:
            pub_dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pub_dt = datetime.now(timezone.utc)

        item = NewsItem(
            title=title,
            description=description[:500],
            url=ev.get("url", ev.get("link", "")),
            source_name="worldmonitor",
            source_type=SignalSource.WORLDMONITOR,
            category=category,
            published_at=pub_dt,
            fetched_at=datetime.now(timezone.utc),
        )

        if not WorldMonitorClient._is_relevant(item):
            return None

        item.keywords_matched = WorldMonitorClient._extract_keywords(item)
        item.relevance_score = min(len(item.keywords_matched) / 5.0, 1.0)
        return item

    async def _interruptible_sleep(self, seconds: float) -> None:
        """Sleep that wakes up early if stop() is called."""
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

