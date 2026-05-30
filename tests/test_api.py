"""
Tests for the FastAPI REST API endpoints.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import _clear_rate_limit_state, app, arq_pool


# =============================================================================
# Test Client
# =============================================================================


@pytest.fixture
def client() -> TestClient:
    """Create a TestClient for the FastAPI app."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_rate_limit_state_fixture() -> None:
    """Ensure in-memory rate limit buckets do not leak across tests."""
    _clear_rate_limit_state()


@pytest.fixture
def mock_arq_pool_fixture(mocker):
    """Mock the global ARQ pool."""
    mock = AsyncMock()
    mock.ping = AsyncMock(return_value=True)

    mock_job = mocker.MagicMock()
    mock_job.job_id = str(uuid.uuid4())

    async def _enqueue(*args, **kwargs):
        return mock_job

    mock.enqueue_job = _enqueue
    mock.close = AsyncMock()

    return mock


# =============================================================================
# Health Endpoint Tests
# =============================================================================


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_returns_200(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "redis_connected" in data

    def test_health_has_version(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.json()["version"] == "0.1.0"


class TestMetricsEndpoint:
    """Tests for GET /metrics."""

    def test_metrics_returns_prometheus_payload(self, client: TestClient) -> None:
        # Generate a request to ensure counters are populated.
        client.get("/health")

        response = client.get("/metrics")
        assert response.status_code == 200
        assert "drawio_http_requests_total" in response.text


# =============================================================================
# Root Endpoint Tests
# =============================================================================


class TestRootEndpoint:
    """Tests for GET /."""

    def test_root_returns_200(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "drawio-automation-platform"


# =============================================================================
# Diagram Generate Endpoint Tests
# =============================================================================


class TestDiagramGenerate:
    """Tests for POST /api/v1/diagram/generate."""

    def test_generate_compliant_diagram_returns_202(self, client: TestClient, mocker) -> None:
        """A compliant diagram should return 202 with status queued."""
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)
        mock_job = mocker.MagicMock()
        mock_job.job_id = str(uuid.uuid4())

        async def _enqueue(*args, **kwargs):
            return mock_job

        mock_pool.enqueue_job = _enqueue

        with patch("api.main.arq_pool", mock_pool):
            payload = {
                "xml_content": """<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/><mxCell id="2" value="Test" style="fillColor=#4A90D9;strokeColor=#333333;" vertex="1" parent="1"><mxGeometry x="100" y="100" width="100" height="100" as="geometry"/></mxCell></root></mxGraphModel>""",
                "export_format": "svg",
                "export_scale": 1.0,
            }
            response = client.post("/api/v1/diagram/generate", json=payload)
            assert response.status_code == 202
            data = response.json()
            assert data["status"] == "queued"
            assert "task_id" in data
            assert data["compliance"]["level"] == "compliant"

    def test_generate_rejected_malformed_xml(self, client: TestClient, mocker) -> None:
        """Malformed XML should return 202 with status rejected."""
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)

        with patch("api.main.arq_pool", mock_pool):
            payload = {
                "xml_content": "<<<not valid xml>>>",
                "export_format": "svg",
            }
            response = client.post("/api/v1/diagram/generate", json=payload)
            assert response.status_code == 202
            data = response.json()
            assert data["status"] == "rejected"
            assert data["compliance"]["level"] == "blocked"

    def test_generate_rejected_disallowed_color(self, client: TestClient, mocker) -> None:
        """A diagram with disallowed colors should be rejected."""
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)

        # Override settings with strict color policy
        with patch("api.main.settings", Settings(
            ALLOWED_COLORS="333333",
            ALLOWED_STENCILS="",
        )):
            with patch("api.main.arq_pool", mock_pool):
                payload = {
                    "xml_content": """<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/><mxCell id="2" value="Red" style="fillColor=#FF0000;strokeColor=#333333;" vertex="1" parent="1"><mxGeometry x="100" y="100" width="100" height="100" as="geometry"/></mxCell></root></mxGraphModel>""",
                    "export_format": "svg",
                }
                response = client.post("/api/v1/diagram/generate", json=payload)
                assert response.status_code == 202
                data = response.json()
                assert data["status"] == "rejected"
                assert len(data["compliance"]["color_violations"]) >= 1

    def test_generate_with_custom_task_id(self, client: TestClient, mocker) -> None:
        """Client-provided task IDs should be preserved."""
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)
        mock_job = mocker.MagicMock()
        mock_job.job_id = str(uuid.uuid4())

        async def _enqueue(*args, **kwargs):
            return mock_job

        mock_pool.enqueue_job = _enqueue

        custom_id = "custom-task-123"

        with patch("api.main.arq_pool", mock_pool):
            payload = {
                "task_id": custom_id,
                "xml_content": """<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel>""",
                "export_format": "png",
            }
            response = client.post("/api/v1/diagram/generate", json=payload)
            assert response.status_code == 202
            data = response.json()
            assert data["task_id"] == custom_id

    def test_generate_validation_error_invalid_format(self, client: TestClient) -> None:
        """Invalid export format should return 422."""
        payload = {
            "xml_content": "<mxGraphModel/>",
            "export_format": "gif",  # Not allowed
        }
        response = client.post("/api/v1/diagram/generate", json=payload)
        assert response.status_code == 422

    def test_generate_with_webhook_url(self, client: TestClient, mocker) -> None:
        """Webhook URL should be accepted."""
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)
        mock_job = mocker.MagicMock()
        mock_job.job_id = str(uuid.uuid4())

        async def _enqueue(*args, **kwargs):
            return mock_job

        mock_pool.enqueue_job = _enqueue

        with patch("api.main.arq_pool", mock_pool):
            payload = {
                "xml_content": """<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel>""",
                "webhook_url": "https://hooks.example.com/callback",
            }
            response = client.post("/api/v1/diagram/generate", json=payload)
            assert response.status_code == 202

    def test_generate_with_metadata(self, client: TestClient, mocker) -> None:
        """Metadata should be accepted in the request."""
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)
        mock_job = mocker.MagicMock()
        mock_job.job_id = str(uuid.uuid4())

        async def _enqueue(*args, **kwargs):
            return mock_job

        mock_pool.enqueue_job = _enqueue

        with patch("api.main.arq_pool", mock_pool):
            payload = {
                "xml_content": """<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel>""",
                "metadata": {"project": "test", "author": "jane"},
            }
            response = client.post("/api/v1/diagram/generate", json=payload)
            assert response.status_code == 202


# =============================================================================
# Task Status Endpoint Tests
# =============================================================================


class TestTaskStatus:
    """Tests for GET /api/v1/diagram/status/{task_id}."""

    def test_status_queued_when_not_found(self, client: TestClient, mocker) -> None:
        """When task is not in ARQ results, should return queued."""
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)
        mock_pool.get_job_result = AsyncMock(return_value=None)

        with patch("api.main.arq_pool", mock_pool):
            response = client.get("/api/v1/diagram/status/nonexistent-task")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "queued"

    def test_status_completed_when_success(self, client: TestClient, mocker) -> None:
        """When task completed successfully, should return completed."""
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)

        class MockJobInfo:
            success = True
            result = {"status": "completed", "s3_url": "https://s3.example.com/file.svg", "message": "Done"}

        mock_pool.get_job_result = AsyncMock(return_value=MockJobInfo())

        with patch("api.main.arq_pool", mock_pool):
            response = client.get("/api/v1/diagram/status/some-task-id")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] in ("completed", "degraded")

    def test_status_failed_when_error(self, client: TestClient, mocker) -> None:
        """When task failed, should return failed."""
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)

        class MockJobInfo:
            success = False
            result = "Rendering timeout error"

        mock_pool.get_job_result = AsyncMock(return_value=MockJobInfo())

        with patch("api.main.arq_pool", mock_pool):
            response = client.get("/api/v1/diagram/status/failed-task")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "failed"

    def test_status_503_when_no_redis(self, client: TestClient) -> None:
        """When ARQ pool is not connected, should return 503."""
        with patch("api.main.arq_pool", None):
            response = client.get("/api/v1/diagram/status/some-task")
            assert response.status_code == 503


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handlers and edge cases."""

    def test_generate_503_when_no_redis(self, client: TestClient) -> None:
        """When ARQ pool is not available, should return 503."""
        with patch("api.main.arq_pool", None):
            payload = {
                "xml_content": """<mxGraphModel><root><mxCell id="0"/></root></mxGraphModel>""",
            }
            response = client.post("/api/v1/diagram/generate", json=payload)
            assert response.status_code == 503

    def test_generate_empty_xml_returns_422(self, client: TestClient, mocker) -> None:
        """Empty XML should return 422 validation error."""
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)

        with patch("api.main.arq_pool", mock_pool):
            payload = {
                "xml_content": "",
            }
            response = client.post("/api/v1/diagram/generate", json=payload)
            assert response.status_code == 422


# =============================================================================
# API Key Authentication Tests
# =============================================================================


class TestAPIKeyAuth:
    """Tests for optional API key auth on business endpoints."""

    def test_generate_requires_auth_header_when_api_key_configured(self, client: TestClient) -> None:
        """When API key is configured, missing Authorization header should return 401."""
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)

        with patch("api.main.settings", Settings(api_key="secret-key")):
            with patch("api.main.arq_pool", mock_pool):
                payload = {
                    "xml_content": """<mxGraphModel><root><mxCell id=\"0\"/></root></mxGraphModel>""",
                    "export_format": "svg",
                }
                response = client.post("/api/v1/diagram/generate", json=payload)
                assert response.status_code == 401

    def test_generate_rejects_invalid_api_key(self, client: TestClient, mocker) -> None:
        """When API key is configured, wrong bearer token should return 403."""
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)
        mock_job = mocker.MagicMock()
        mock_job.job_id = str(uuid.uuid4())

        async def _enqueue(*args, **kwargs):
            return mock_job

        mock_pool.enqueue_job = _enqueue

        with patch("api.main.settings", Settings(api_key="secret-key")):
            with patch("api.main.arq_pool", mock_pool):
                payload = {
                    "xml_content": """<mxGraphModel><root><mxCell id=\"0\"/></root></mxGraphModel>""",
                    "export_format": "svg",
                }
                response = client.post(
                    "/api/v1/diagram/generate",
                    json=payload,
                    headers={"Authorization": "Bearer wrong-key"},
                )
                assert response.status_code == 403

    def test_generate_accepts_valid_api_key(self, client: TestClient, mocker) -> None:
        """When API key is configured, matching bearer token should allow request."""
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)
        mock_job = mocker.MagicMock()
        mock_job.job_id = str(uuid.uuid4())

        async def _enqueue(*args, **kwargs):
            return mock_job

        mock_pool.enqueue_job = _enqueue

        with patch("api.main.settings", Settings(api_key="secret-key")):
            with patch("api.main.arq_pool", mock_pool):
                payload = {
                    "xml_content": """<mxGraphModel><root><mxCell id=\"0\"/></root></mxGraphModel>""",
                    "export_format": "svg",
                }
                response = client.post(
                    "/api/v1/diagram/generate",
                    json=payload,
                    headers={"Authorization": "Bearer secret-key"},
                )
                assert response.status_code == 202
                assert response.json()["status"] in ("queued", "rejected")

    def test_status_requires_auth_header_when_api_key_configured(self, client: TestClient) -> None:
        """Status endpoint should also enforce auth when API key is configured."""
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)
        mock_pool.get_job_result = AsyncMock(return_value=None)

        with patch("api.main.settings", Settings(api_key="secret-key")):
            with patch("api.main.arq_pool", mock_pool):
                response = client.get("/api/v1/diagram/status/some-task")
                assert response.status_code == 401


# =============================================================================
# Rate Limiting Tests
# =============================================================================


class TestRateLimiting:
    """Tests for per-IP rate limits on business endpoints."""

    def test_generate_rate_limit_returns_429_when_exceeded(self, client: TestClient, mocker) -> None:
        """Generate endpoint should reject requests above configured per-minute limit."""
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)
        mock_job = mocker.MagicMock()
        mock_job.job_id = str(uuid.uuid4())

        async def _enqueue(*args, **kwargs):
            return mock_job

        mock_pool.enqueue_job = _enqueue

        with patch("api.main.settings", Settings(rate_limit_generate_per_minute=1, rate_limit_status_per_minute=1000)):
            with patch("api.main.arq_pool", mock_pool):
                payload = {
                    "xml_content": """<mxGraphModel><root><mxCell id=\"0\"/></root></mxGraphModel>""",
                    "export_format": "svg",
                }
                first = client.post("/api/v1/diagram/generate", json=payload)
                second = client.post("/api/v1/diagram/generate", json=payload)

                assert first.status_code == 202
                assert second.status_code == 429

    def test_status_rate_limit_returns_429_when_exceeded(self, client: TestClient) -> None:
        """Status endpoint should reject requests above configured per-minute limit."""
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)
        mock_pool.get_job_result = AsyncMock(return_value=None)

        with patch("api.main.settings", Settings(rate_limit_generate_per_minute=1000, rate_limit_status_per_minute=1)):
            with patch("api.main.arq_pool", mock_pool):
                first = client.get("/api/v1/diagram/status/task-1")
                second = client.get("/api/v1/diagram/status/task-2")

                assert first.status_code == 200
                assert second.status_code == 429


class TestPayloadLimits:
    """Tests for XML payload size enforcement."""

    def test_generate_rejects_payload_exceeding_limit(self, client: TestClient) -> None:
        """Payload larger than MAX_XML_PAYLOAD_SIZE should return 413."""
        mock_pool = AsyncMock()
        mock_pool.ping = AsyncMock(return_value=True)

        oversized_xml = "x" * 200
        with patch("api.main.settings", Settings(max_xml_payload_size=100)):
            with patch("api.main.arq_pool", mock_pool):
                payload = {
                    "xml_content": oversized_xml,
                    "export_format": "svg",
                }
                response = client.post("/api/v1/diagram/generate", json=payload)
                assert response.status_code == 413