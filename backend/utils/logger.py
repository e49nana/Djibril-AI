"""
Djibril AI — Structured Logger

Provides JSON-structured logging via structlog with:
- Per-module log levels
- File rotation (10 MB, 5 backups)
- @timed decorator for performance measurement
- Colored console output in development
"""

from __future__ import annotations

import functools
import logging
import logging.handlers
import sys
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

import structlog

from .config import get_settings

F = TypeVar("F", bound=Callable[..., Any])

_initialized = False


def setup_logging() -> None:
    """Initialize the global logging pipeline. Idempotent — safe to call multiple times."""
    global _initialized
    if _initialized:
        return

    cfg = get_settings().log
    log_path = cfg.log_path
    log_level = getattr(logging, cfg.level.upper(), logging.INFO)

    # ── stdlib root handler: rotating file ──
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_path / "djibril.log"),
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)

    # ── console handler ──
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # ── configure stdlib root ──
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=[file_handler, console_handler],
        force=True,
    )

    # ── structlog processors ──
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # ── formatters for handlers ──
    json_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
        foreign_pre_chain=shared_processors,
    )

    file_handler.setFormatter(json_formatter)
    console_handler.setFormatter(console_formatter)

    _initialized = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a named structlog logger. Initializes logging on first call.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        A structlog BoundLogger instance.
    """
    setup_logging()
    return structlog.get_logger(name)


def timed(func: F) -> F:
    """Decorator that logs function execution time.

    Works with both sync and async functions. Logs at INFO level
    with the function name and elapsed milliseconds.

    Args:
        func: The function to wrap.

    Returns:
        Wrapped function with timing instrumentation.
    """
    logger = get_logger(func.__module__)

    if _is_coroutine(func):
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.info(
                    "function_completed",
                    function=func.__qualname__,
                    elapsed_ms=round(elapsed_ms, 2),
                )
                return result
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.error(
                    "function_failed",
                    function=func.__qualname__,
                    elapsed_ms=round(elapsed_ms, 2),
                    error=str(exc),
                )
                raise

        return async_wrapper  # type: ignore[return-value]
    else:
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.info(
                    "function_completed",
                    function=func.__qualname__,
                    elapsed_ms=round(elapsed_ms, 2),
                )
                return result
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.error(
                    "function_failed",
                    function=func.__qualname__,
                    elapsed_ms=round(elapsed_ms, 2),
                    error=str(exc),
                )
                raise

        return sync_wrapper  # type: ignore[return-value]


def _is_coroutine(func: Callable[..., Any]) -> bool:
    """Check if a function is a coroutine function."""
    import asyncio
    return asyncio.iscoroutinefunction(func)
