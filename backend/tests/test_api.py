"""
Djibril AI — REST API tests

Exercise the FastAPI app in-process (no network, no API keys): health,
signal endpoints on an empty database, geo score default and API-key auth.
"""

import os
import sys
import tempfile

import pytest

_TMP = tempfile.mkdtemp(prefix="djibril-api-tests-")
os.environ.setdefault("AGENT_DB_PATH", os.path.join(_TMP, "djibril_memory.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from api.api_server import app  # noqa: E402
from utils.config import get_settings  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    """App client running in an empty temp directory (fresh SQLite files)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(get_settings().server, "api_key", "")
    with TestClient(app) as c:
        yield c


class TestHealth:
    def test_health_ok(self, client) -> None:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "timestamp" in body


class TestSignals:
    def test_latest_is_404_without_signals(self, client) -> None:
        r = client.get("/api/signal/latest")
        assert r.status_code == 404

    def test_history_is_empty_list(self, client) -> None:
        r = client.get("/api/signal/history", params={"limit": 5})
        assert r.status_code == 200
        assert r.json() == []

    def test_geo_score_defaults_to_neutral(self, client) -> None:
        r = client.get("/api/geo-score")
        assert r.status_code == 200
        assert r.json()["score"] == 0


class TestAuth:
    def test_wrong_key_is_rejected(self, client, monkeypatch) -> None:
        monkeypatch.setattr(get_settings().server, "api_key", "s3cret")
        assert client.get("/api/geo-score").status_code == 403
        assert client.get("/api/geo-score", headers={"X-API-Key": "nope"}).status_code == 403

    def test_right_key_is_accepted(self, client, monkeypatch) -> None:
        monkeypatch.setattr(get_settings().server, "api_key", "s3cret")
        r = client.get("/api/geo-score", headers={"X-API-Key": "s3cret"})
        assert r.status_code == 200

    def test_health_needs_no_key(self, client, monkeypatch) -> None:
        monkeypatch.setattr(get_settings().server, "api_key", "s3cret")
        assert client.get("/health").status_code == 200
