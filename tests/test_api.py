"""
Tests de la API REST del normalizador C4 (POST /api/v1/diagram/normalize).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import _clear_rate_limit_state, app

# Crudo de IA real usado como entrada de referencia.
_FIXTURE = Path(__file__).parent / "fixtures" / "crudo_ia_2_simple.drawio.xml"
RAW_XML = _FIXTURE.read_text(encoding="utf-8")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_rate_limit() -> None:
    """Evita que los buckets de rate limit se filtren entre tests."""
    _clear_rate_limit_state()


# =============================================================================
# Health / Metrics / Root
# =============================================================================


class TestHealth:
    def test_health_returns_200(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"
        assert data["layout_engine"] in ("elk", "layered")

    def test_health_reports_environment(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["environment"] in ("dev", "prod")


class TestMetrics:
    def test_metrics_returns_prometheus_payload(self, client: TestClient) -> None:
        client.get("/health")
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "drawio_http_requests_total" in response.text


class TestRoot:
    def test_root_returns_200(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["service"] == "drawio-automation-platform"


# =============================================================================
# /api/v1/diagram/normalize
# =============================================================================


class TestNormalize:
    def test_returns_c4_xml(self, client: TestClient) -> None:
        response = client.post("/api/v1/diagram/normalize", json={"xml_content": RAW_XML, "c4_level": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["xml_c4"].lstrip().startswith("<")
        assert "mxfile" in data["xml_c4"] or "mxGraphModel" in data["xml_c4"]
        assert data["report"]["node_count"] >= 1
        assert data["report"]["engine"]  # non-empty engine name
        assert data["compliance"] is None  # not requested

    def test_compliance_when_requested(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/diagram/normalize",
            json={"xml_content": RAW_XML, "run_compliance_check": True},
        )
        assert response.status_code == 200
        compliance = response.json()["compliance"]
        assert compliance is not None
        assert compliance["level"] in ("compliant", "warning", "blocked")

    def test_title_block_accepted(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/diagram/normalize",
            json={
                "xml_content": RAW_XML,
                "c4_level": 2,
                "title_block": {
                    "project": "BFCL",
                    "title": "Arquitectura As-Is",
                    "doc_type": "As-Is",
                    "approved_by": "Camila",
                    "revision": "A",
                },
            },
        )
        assert response.status_code == 200

    def test_invalid_level_returns_422(self, client: TestClient) -> None:
        response = client.post("/api/v1/diagram/normalize", json={"xml_content": RAW_XML, "c4_level": 9})
        assert response.status_code == 422

    def test_empty_xml_returns_422(self, client: TestClient) -> None:
        response = client.post("/api/v1/diagram/normalize", json={"xml_content": ""})
        assert response.status_code == 422

    def test_payload_too_large_returns_413(self, client: TestClient) -> None:
        with patch("api.main.settings", Settings(max_xml_payload_size=50)):
            response = client.post("/api/v1/diagram/normalize", json={"xml_content": "x" * 200})
            assert response.status_code == 413


# =============================================================================
# Autenticación opcional (API key)
# =============================================================================


class TestAPIKeyAuth:
    def test_missing_key_returns_401(self, client: TestClient) -> None:
        with patch("api.main.settings", Settings(api_key="secret-key")):
            response = client.post("/api/v1/diagram/normalize", json={"xml_content": RAW_XML})
            assert response.status_code == 401

    def test_wrong_key_returns_403(self, client: TestClient) -> None:
        with patch("api.main.settings", Settings(api_key="secret-key")):
            response = client.post(
                "/api/v1/diagram/normalize",
                json={"xml_content": RAW_XML},
                headers={"Authorization": "Bearer wrong-key"},
            )
            assert response.status_code == 403

    def test_valid_key_returns_200(self, client: TestClient) -> None:
        with patch("api.main.settings", Settings(api_key="secret-key")):
            response = client.post(
                "/api/v1/diagram/normalize",
                json={"xml_content": RAW_XML},
                headers={"Authorization": "Bearer secret-key"},
            )
            assert response.status_code == 200


# =============================================================================
# Rate limiting
# =============================================================================


class TestRateLimiting:
    def test_429_when_exceeded(self, client: TestClient) -> None:
        with patch("api.main.settings", Settings(rate_limit_normalize_per_minute=1)):
            first = client.post("/api/v1/diagram/normalize", json={"xml_content": RAW_XML})
            second = client.post("/api/v1/diagram/normalize", json={"xml_content": RAW_XML})
            assert first.status_code == 200
            assert second.status_code == 429
