"""
Djibril AI — Main Orchestrator

Runs the full pipeline on schedule:
- News scan every 2 minutes
- AI scoring every 5 minutes
- Signal check every 30 seconds
- SQLite cleanup weekly

Handles SIGTERM/SIGINT for graceful shutdown.
"""

from __future__ import annotations

import asyncio
import os
import signal as os_signal
import sys
from datetime import datetime, timezone
from typing import List, Optional

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except ImportError:
    AsyncIOScheduler = None  # type: ignore

try:
    from utils.config import get_settings
    from utils.logger import get_logger, timed
    from utils.models import GeoSignal, NewsItem, TradeAction
    from collectors.rss_aggregator import RSSAggregator
    from collectors.worldmonitor_client import WorldMonitorClient, WorldMonitorWSClient
    from collectors.news_fetcher import NewsFetcher
    from scoring.claude_scorer import ClaudeScorer
    from scoring.sentiment_analyzer import SentimentAnalyzer
    from scoring.technical_analyzer import TechnicalAnalyzer
    from scoring.geo_risk_engine import GeoRiskEngine
    from signals.signal_composer import SignalComposer
    from signals.signal_publisher import SignalPublisher
    from signals.alerts import AlertManager
    from agent.memory import get_memory
    from agent.djibril_agent import get_agent
except ImportError:
    # Handle relative imports for package mode
    from .utils.config import get_settings  # type: ignore
    from .utils.logger import get_logger, timed  # type: ignore
    # ... (same pattern)

logger = get_logger(__name__)


class DjibrilOrchestrator:
    """Main orchestrator that ties together all system components.

    Schedules periodic tasks: news collection, scoring, signal
    generation, and cleanup. Supports graceful shutdown.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._shutdown_event = asyncio.Event()
        self._news_queue: asyncio.Queue[NewsItem] = asyncio.Queue(maxsize=1000)

        # Components
        self._rss = RSSAggregator()
        self._worldmonitor = WorldMonitorClient()
        self._newsapi = NewsFetcher(event_queue=self._news_queue)
        self._claude_scorer = ClaudeScorer()
        self._sentiment = SentimentAnalyzer()
        self._technical = TechnicalAnalyzer()
        self._risk_engine = GeoRiskEngine()
        self._composer = SignalComposer()
        self._publisher = SignalPublisher()
        self._alerts = AlertManager()

        # WorldMonitor WebSocket client
        self._wm_ws = WorldMonitorWSClient()
        self._wm_event_queue: asyncio.Queue[NewsItem] = asyncio.Queue(maxsize=500)
        self._wm_ws._queue = self._wm_event_queue

        # Agent v2.0
        self._memory = get_memory()
        self._agent = get_agent()

        # State
        self._latest_news: List[NewsItem] = []
        self._latest_signal: Optional[GeoSignal] = None
        self._running = False

        # Keywords that trigger immediate re-scoring
        self._urgent_keywords: set[str] = {
            "iran", "hormuz", "irgc", "strike", "attack",
            "blockade", "missiles", "missile",
        }

    async def start(self) -> None:
        """Start the orchestrator with scheduled tasks and WS connections."""
        logger.info("orchestrator_starting")
        self._running = True

        tasks = [
            asyncio.create_task(self._start_scheduler()),
            asyncio.create_task(self._run_wm_ws()),
            asyncio.create_task(self._consume_wm_events()),
        ]

        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            self._running = False
            logger.info("orchestrator_stopped")

    async def _start_scheduler(self) -> None:
        """Run the APScheduler loop until shutdown is requested."""
        if AsyncIOScheduler is None:
            logger.error("apscheduler_not_installed")
            return

        scheduler = AsyncIOScheduler()
        cfg = self._settings.signal

        scheduler.add_job(
            self.scan_news, "interval",
            minutes=cfg.scan_interval_minutes, id="scan_news", max_instances=1,
        )
        scheduler.add_job(
            self.run_scoring, "interval",
            minutes=cfg.scoring_interval_minutes, id="run_scoring", max_instances=1,
        )
        scheduler.add_job(
            self.check_signal, "interval",
            seconds=cfg.signal_check_interval_seconds, id="check_signal", max_instances=1,
        )
        scheduler.add_job(
            self.cleanup, "cron", day_of_week="sun", hour=3, id="weekly_cleanup",
        )

        # Initialize agent memory
        await self._memory.initialize()
        logger.info("agent_memory_initialized")

        scheduler.start()
        logger.info(
            "orchestrator_scheduled",
            scan_interval=cfg.scan_interval_minutes,
            scoring_interval=cfg.scoring_interval_minutes,
            signal_check=cfg.signal_check_interval_seconds,
        )

        # Initial scan
        await self.scan_news()
        await self.run_scoring()

        # Wait for shutdown
        try:
            await self._shutdown_event.wait()
        finally:
            scheduler.shutdown(wait=False)
            await self._worldmonitor.close()

    async def _run_wm_ws(self) -> None:
        """Launch the WorldMonitor WebSocket client with crash recovery."""
        while not self._shutdown_event.is_set():
            try:
                logger.info("wm_ws_task_starting")
                await self._wm_ws.run()
            except Exception as exc:
                logger.error("wm_ws_task_crashed", error=str(exc))
                # Wait before restarting — don't take down the whole system
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=30)
                    return  # shutdown requested during wait
                except asyncio.TimeoutError:
                    pass  # 30s elapsed, retry

    async def _consume_wm_events(self) -> None:
        """Consume WorldMonitor WS events from the queue.

        Triggers immediate re-scoring if the event contains urgent keywords
        (iran, hormuz, strike, etc.). Otherwise appends to the news buffer
        for the next scheduled scoring cycle. Always broadcasts to the
        dashboard via WebSocket.
        """
        try:
            from api.websocket_manager import ws_manager
        except ImportError:
            ws_manager = None  # type: ignore

        while not self._shutdown_event.is_set():
            try:
                item = await asyncio.wait_for(
                    self._wm_event_queue.get(), timeout=5.0,
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            # Determine urgency from keywords
            matched_urgent = self._urgent_keywords & set(item.keywords_matched)
            trigger_rescore = len(matched_urgent) > 0

            # Always add to latest news
            self._latest_news.append(item)

            # Broadcast to dashboard
            if ws_manager is not None:
                try:
                    await ws_manager.broadcast_news(
                        [item.model_dump(mode="json")]
                    )
                except Exception as exc:
                    logger.debug("wm_ws_broadcast_failed", error=str(exc))

            logger.info(
                "wm_event_received",
                title=item.title[:60],
                keywords=list(matched_urgent) if matched_urgent else [],
                triggered_rescore=trigger_rescore,
            )

            # Record high-relevance events in agent memory
            if len(item.keywords_matched) >= 2:
                try:
                    geo_score_val = (
                        self._latest_signal.geo_score.score
                        if self._latest_signal
                        else 0
                    )
                    await self._memory.record_event(
                        item,
                        geo_score=geo_score_val,
                        urgency="high" if trigger_rescore else "low",
                    )
                except Exception as exc:
                    logger.debug("memory_event_record_failed", error=str(exc))

            # Immediate re-scoring for urgent events
            if trigger_rescore:
                try:
                    await self.run_scoring()
                    await self.check_signal()
                except Exception as exc:
                    logger.error("wm_urgent_rescore_failed", error=str(exc))

    @timed
    async def scan_news(self) -> None:
        """Collect news from all sources."""
        logger.info("scan_news_start")

        all_items: List[NewsItem] = []

        # RSS feeds
        try:
            rss_items = await self._rss.fetch_all_feeds()
            all_items.extend(rss_items)
        except Exception as exc:
            logger.error("scan_rss_failed", error=str(exc))

        # WorldMonitor
        try:
            wm_items = await self._worldmonitor.fetch_events()
            all_items.extend(wm_items)
        except Exception as exc:
            logger.error("scan_worldmonitor_failed", error=str(exc))

        # NewsAPI
        try:
            news_items = await self._newsapi.fetch_all()
            all_items.extend(news_items)
        except Exception as exc:
            logger.error("scan_newsapi_failed", error=str(exc))

        # Deduplicate across sources by title hash
        seen: set[str] = set()
        unique: List[NewsItem] = []
        for item in all_items:
            if item.title_hash not in seen:
                seen.add(item.title_hash)
                unique.append(item)

        self._latest_news = unique
        logger.info("scan_news_complete", total=len(unique))

    @timed
    async def run_scoring(self) -> None:
        """Score the latest news and produce a GeoSignal."""
        if not self._latest_news:
            logger.info("scoring_no_news")
            return

        logger.info("scoring_start", headlines=len(self._latest_news))

        # 1. Geo score via Claude
        geo_score = self._claude_scorer.score_headlines(self._latest_news)

        # 2. Technical analysis
        tech_score = self._technical.analyze()

        # 3. Sentiment analysis
        sentiment_score = await self._sentiment.analyze()

        # 4. Risk engine aggregation
        self._latest_signal = self._risk_engine.compute_signal(
            geo_score=geo_score,
            technical_score=tech_score,
            sentiment_score=sentiment_score,
        )

        logger.info(
            "scoring_complete",
            composite=self._latest_signal.composite_score,
            action=self._latest_signal.suggested_action.value,
            confidence=self._latest_signal.confidence,
        )

    @timed
    async def check_signal(self) -> None:
        """Check the latest signal and publish if actionable."""
        if self._latest_signal is None:
            return

        trade_signal = self._composer.compose(self._latest_signal)

        # Publish all signals (including FLAT for dashboard)
        await self._publisher.publish(trade_signal)

        # Record signal in agent memory
        try:
            await self._memory.record_signal(trade_signal)
        except Exception as exc:
            logger.debug("memory_record_signal_failed", error=str(exc))

        # Record price snapshot for outcome tracking
        try:
            if self._latest_signal and self._latest_signal.technical_score.current_price > 0:
                await self._memory.record_price_snapshot(
                    "WTI", self._latest_signal.technical_score.current_price
                )
        except Exception as exc:
            logger.debug("memory_price_snapshot_failed", error=str(exc))

        # Send alert for actionable signals
        if trade_signal.action != TradeAction.FLAT:
            await self._alerts.send_signal_alert(trade_signal)

            # Generate and broadcast agent brief
            try:
                from api.websocket_manager import ws_manager
                brief = await self._agent.quick_brief()
                await ws_manager.broadcast_agent_brief(brief)
            except Exception as exc:
                logger.debug("agent_brief_failed", error=str(exc))

    async def force_scan(self) -> None:
        """Force an immediate full scan + score + signal cycle."""
        logger.info("force_scan_triggered")
        await self.scan_news()
        await self.run_scoring()
        await self.check_signal()

    def cleanup(self) -> None:
        """Weekly cleanup of old data."""
        logger.info("cleanup_start")
        try:
            self._rss.cleanup_old(keep_days=30)
        except Exception as exc:
            logger.error("cleanup_failed", error=str(exc))

    def shutdown(self) -> None:
        """Signal the orchestrator to shut down gracefully."""
        logger.info("shutdown_requested")
        self._shutdown_event.set()
        # Schedule WS stop (non-blocking from sync context)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._wm_ws.stop())
        except RuntimeError:
            pass

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def latest_signal(self) -> Optional[GeoSignal]:
        return self._latest_signal

    @property
    def latest_news(self) -> List[NewsItem]:
        return self._latest_news

    @property
    def health_status(self) -> dict:
        """System health info including WorldMonitor WS status."""
        return {
            "running": self._running,
            "latest_news_count": len(self._latest_news),
            "worldmonitor_ws": {
                "connected": self._wm_ws.is_connected,
                "reconnects": self._wm_ws.reconnect_count,
                "last_event": (
                    self._wm_ws.last_event_at.isoformat()
                    if self._wm_ws.last_event_at
                    else None
                ),
            },
        }


def _setup_signal_handlers(orchestrator: DjibrilOrchestrator) -> None:
    """Register OS signal handlers for graceful shutdown."""
    try:
        loop = asyncio.get_running_loop()
        for sig in (os_signal.SIGTERM, os_signal.SIGINT):
            loop.add_signal_handler(sig, orchestrator.shutdown)
    except (NotImplementedError, RuntimeError):
        # Windows or no running loop
        pass


async def main() -> None:
    """Entry point for the Djibril AI backend."""
    orchestrator = DjibrilOrchestrator()
    _setup_signal_handlers(orchestrator)
    await orchestrator.start()


if __name__ == "__main__":
    asyncio.run(main())
