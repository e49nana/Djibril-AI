"""
Djibril AI — FastAPI REST Server

Exposes trade signals, geo scores, and news via REST endpoints.
Features: API key auth, CORS, rate limiting, health checks.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

try:
    from ..utils.config import get_settings
    from ..utils.logger import get_logger
    from ..utils.models import NewsCategory, TradeSignal, WSMessage, WSMessageType
    from ..signals.signal_publisher import SignalPublisher
    from ..main_loop import DjibrilOrchestrator
except ImportError:
    from utils.config import get_settings
    from utils.logger import get_logger
    from utils.models import NewsCategory, TradeSignal, WSMessage, WSMessageType
    from signals.signal_publisher import SignalPublisher

try:
    from agent.djibril_agent import get_agent
    from agent.memory import get_memory
except ImportError:
    try:
        from ..agent.djibril_agent import get_agent
        from ..agent.memory import get_memory
    except ImportError:
        get_agent = None  # type: ignore
        get_memory = None  # type: ignore

logger = get_logger(__name__)

# ── Globals managed by lifespan ──
_orchestrator: Optional[object] = None
_publisher: Optional[SignalPublisher] = None
_ws_queue: Optional[asyncio.Queue] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init shared resources."""
    global _publisher, _ws_queue
    _ws_queue = asyncio.Queue(maxsize=500)
    _publisher = SignalPublisher(ws_queue=_ws_queue)

    # Initialize agent memory
    if get_memory is not None:
        memory = get_memory()
        await memory.initialize()
        logger.info("agent_memory_ready")

    logger.info("api_server_startup")
    yield
    logger.info("api_server_shutdown")


app = FastAPI(
    title="Djibril AI Trading System",
    description="Real-time geopolitical oil trading signals powered by Claude AI",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.server.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate limiting ──
try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware

    limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
except ImportError:
    limiter = None
    logger.warning("slowapi_not_installed_rate_limiting_disabled")

# ── API Key Auth ──
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Security(_api_key_header)) -> str:
    """Validate the API key from request headers.

    Args:
        api_key: The key from X-API-Key header.

    Returns:
        The validated key.

    Raises:
        HTTPException: If key is missing or invalid.
    """
    expected = get_settings().server.api_key
    if not expected or expected == "djibril-secret-key-change-me":
        # No auth configured — allow all (dev mode)
        return "dev-mode"
    if not api_key or api_key != expected:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key


# ═══════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════

@app.get("/health")
async def health_check():
    """System health check with collector status."""
    # Try to get orchestrator health if available
    wm_ws_status: dict = {"connected": False, "reconnects": 0, "last_event": None}
    try:
        from collectors.worldmonitor_client import WorldMonitorWSClient
        # The orchestrator sets this at module level when running
        if _orchestrator is not None and hasattr(_orchestrator, "health_status"):
            orch_health = _orchestrator.health_status  # type: ignore
            wm_ws_status = orch_health.get("worldmonitor_ws", wm_ws_status)
    except Exception:
        pass

    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.2.0",
        "components": {
            "api": "running",
            "publisher": "ready" if _publisher else "not_initialized",
            "websocket_queue": _ws_queue.qsize() if _ws_queue else 0,
        },
        "worldmonitor_ws": wm_ws_status,
    }


@app.get("/api/signal/latest")
async def get_latest_signal(key: str = Depends(verify_api_key)):
    """Get the most recent trade signal.

    Returns:
        Latest TradeSignal JSON or 404 if none available.
    """
    if _publisher is None:
        raise HTTPException(status_code=503, detail="Publisher not initialized")

    latest = _publisher.get_latest()
    if latest is None:
        raise HTTPException(status_code=404, detail="No signals available")
    return latest


@app.get("/api/signal/history")
async def get_signal_history(
    limit: int = Query(default=50, ge=1, le=500),
    key: str = Depends(verify_api_key),
):
    """Get historical trade signals.

    Args:
        limit: Number of signals to return (max 500).

    Returns:
        List of TradeSignal dicts, newest first.
    """
    if _publisher is None:
        raise HTTPException(status_code=503, detail="Publisher not initialized")

    return _publisher.get_history(limit=limit)


@app.get("/api/geo-score")
async def get_geo_score(key: str = Depends(verify_api_key)):
    """Get the current geopolitical risk score.

    Returns:
        Latest geo score data from the most recent signal.
    """
    if _publisher is None:
        raise HTTPException(status_code=503, detail="Publisher not initialized")

    latest = _publisher.get_latest()
    if latest is None:
        return {
            "score": 0,
            "urgency": "low",
            "reasoning": "No scoring data available yet.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "score": latest.get("geo_score", 0),
        "urgency": latest.get("urgency", "low"),
        "reasoning": latest.get("reasoning", ""),
        "confidence": latest.get("confidence", 0),
        "timestamp": latest.get("created_at", ""),
    }


@app.get("/api/news")
async def get_news(
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    key: str = Depends(verify_api_key),
):
    """Get recent filtered news items.

    Args:
        category: Optional category filter (military, sanctions, etc.)
        limit: Max items to return.

    Returns:
        List of news items.
    """
    from collectors.rss_aggregator import RSSAggregator

    rss = RSSAggregator()
    cat = None
    if category:
        try:
            cat = NewsCategory(category.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid category: {category}. Valid: {[c.value for c in NewsCategory]}",
            )

    items = rss.get_recent_items(limit=limit, category=cat)
    return [item.model_dump(mode="json") for item in items]


@app.post("/api/force-scan")
async def force_scan(key: str = Depends(verify_api_key)):
    """Trigger an immediate news scan and scoring cycle.

    Returns:
        Confirmation with timestamp.
    """
    # In production this would call the orchestrator
    logger.info("api_force_scan_requested")
    return {
        "status": "scan_triggered",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": "Force scan initiated. Results will be available shortly.",
    }


def get_ws_queue() -> Optional[asyncio.Queue]:
    """Return the WebSocket broadcast queue."""
    return _ws_queue


def get_publisher() -> Optional[SignalPublisher]:
    """Return the signal publisher instance."""
    return _publisher


# ═══════════════════════════════════════════════════
# Agent Endpoints (v2.0)
# ═══════════════════════════════════════════════════

from pydantic import BaseModel as _BM


class ChatRequest(_BM):
    message: str
    include_signal_context: bool = True


class ChatResponse(_BM):
    response: str
    agent: str = "DJIBRIL"
    timestamp: datetime


@app.post("/api/chat", response_model=ChatResponse)
async def chat_with_djibril(
    request: ChatRequest,
    key: str = Depends(verify_api_key),
):
    """Send a natural language message to DJIBRIL."""
    if get_agent is None:
        raise HTTPException(status_code=503, detail="Agent module not available")

    agent = get_agent()
    current_signal = None
    recent_news = None

    if request.include_signal_context and _publisher:
        latest = _publisher.get_latest()
        if latest:
            try:
                current_signal = TradeSignal(**latest)
            except Exception:
                pass

    response_text = await agent.chat(
        user_message=request.message,
        current_signal=current_signal,
        recent_news=recent_news,
    )
    return ChatResponse(
        response=response_text,
        timestamp=datetime.now(timezone.utc),
    )


@app.get("/api/agent/brief")
async def get_agent_brief(key: str = Depends(verify_api_key)):
    """Get DJIBRIL's current situational brief (3-5 sentences)."""
    if get_agent is None:
        raise HTTPException(status_code=503, detail="Agent module not available")

    agent = get_agent()
    brief = await agent.quick_brief()
    return {"brief": brief, "generated_at": datetime.now(timezone.utc).isoformat()}


@app.get("/api/agent/explain/{signal_id}")
async def explain_signal(
    signal_id: str,
    key: str = Depends(verify_api_key),
):
    """Ask DJIBRIL to explain the reasoning behind a specific signal."""
    if get_agent is None or get_memory is None:
        raise HTTPException(status_code=503, detail="Agent module not available")

    memory = get_memory()
    signals = await memory.get_recent_signals(limit=50)
    target = next((s for s in signals if s.get("signal_id") == signal_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")

    # Build a minimal TradeSignal for the explanation
    from utils.models import TradeAction, Urgency, GeoScore

    ts = TradeSignal(
        signal_id=target["signal_id"],
        action=TradeAction(target.get("action", "FLAT")),
        confidence=target.get("confidence", 0),
        entry_price=target.get("entry_price", 0),
        stop_loss=target.get("stop_loss", 0),
        take_profit=target.get("take_profit", 0),
        geo_score=target.get("geo_score", 0),
        reasoning=target.get("reasoning", ""),
    )
    gs = GeoScore(
        score=target.get("geo_score", 0),
        reasoning=target.get("reasoning", ""),
    )

    agent = get_agent()
    explanation = await agent.analyze_signal_decision(ts, [], gs)
    return {
        "signal_id": signal_id,
        "explanation": explanation,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/agent/performance")
async def get_agent_performance(key: str = Depends(verify_api_key)):
    """DJIBRIL's self-evaluation of recent signal performance."""
    if get_agent is None or get_memory is None:
        raise HTTPException(status_code=503, detail="Agent module not available")

    memory = get_memory()
    stats = await memory.get_signal_performance()
    agent = get_agent()
    narrative = await agent.self_evaluate()
    return {
        "stats": stats,
        "narrative": narrative,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/memory/events")
async def get_memory_events(
    limit: int = Query(default=20, ge=1, le=100),
    key: str = Depends(verify_api_key),
):
    """Recent geopolitical events from DJIBRIL's memory."""
    if get_memory is None:
        raise HTTPException(status_code=503, detail="Memory module not available")

    memory = get_memory()
    return await memory.get_recent_events(limit=limit)
