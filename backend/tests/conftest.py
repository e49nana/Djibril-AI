"""Shared test setup.

The signal publisher and the agent memory write files relative to the
working directory by default (./mql5/signals, ./djibril_memory.db). Point
them at a temporary directory so a test run never touches the repository.
"""

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="djibril-tests-")
os.environ.setdefault("SIGNAL_OUTPUT_DIR", os.path.join(_TMP, "signals"))
os.environ.setdefault("AGENT_DB_PATH", os.path.join(_TMP, "djibril_memory.db"))
os.environ.setdefault("LOG_DIR", os.path.join(_TMP, "logs"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
