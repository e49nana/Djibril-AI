"""Tests for Step 2 — logger.py validation."""

import asyncio
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.logger import get_logger, setup_logging, timed


class TestLogger:
    def test_setup_idempotent(self) -> None:
        setup_logging()
        setup_logging()  # Should not raise

    def test_get_logger(self) -> None:
        log = get_logger("test_module")
        assert log is not None
        log.info("test_event", key="value")

    def test_log_file_created(self) -> None:
        setup_logging()
        log = get_logger("test_file_check")
        log.info("file_check")
        # Log dir should exist
        from utils.config import get_settings
        assert get_settings().log.log_path.exists()


class TestTimedDecorator:
    def test_sync_function(self) -> None:
        @timed
        def slow_func() -> str:
            time.sleep(0.05)
            return "done"

        result = slow_func()
        assert result == "done"

    def test_async_function(self) -> None:
        @timed
        async def async_func() -> int:
            await asyncio.sleep(0.05)
            return 42

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(async_func())
            assert result == 42
        finally:
            loop.close()

    def test_exception_logged(self) -> None:
        @timed
        def failing_func() -> None:
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            failing_func()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
