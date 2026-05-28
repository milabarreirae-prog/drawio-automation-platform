"""
Pytest fixtures and configuration for drawio-automation-platform tests.

Provides:
- Mock Redis and ARQ pool
- Sample Draw.io XML for testing
- Shared test settings
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# Test XML Samples
# =============================================================================


@pytest.fixture
def valid_xml_basic() -> str:
    """A basic valid Draw.io XML without stencils."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<mxGraphModel dx="1422" dy="794" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="827" pageHeight="1169" math="0" shadow="0">
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
    <mxCell id="2" value="Hello World" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#4A90D9;strokeColor=#333333;fontColor=#1A1A1A;" vertex="1" parent="1">
      <mxGeometry x="360" y="200" width="120" height="60" as="geometry"/>
    </mxCell>
  </root>
</mxGraphModel>"""


@pytest.fixture
def valid_xml_with_aws() -> str:
    """Draw.io XML with AWS stencil shapes."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<mxGraphModel>
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
    <mxCell id="2" value="EC2" style="shape=aws4.instance;fillColor=#4A90D9;strokeColor=#333333;" vertex="1" parent="1">
      <mxGeometry x="200" y="150" width="80" height="80" as="geometry"/>
    </mxCell>
  </root>
</mxGraphModel>"""


@pytest.fixture
def valid_xml_with_archimate() -> str:
    """Draw.io XML with ArchiMate stencil shapes."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<mxGraphModel>
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
    <mxCell id="2" value="Application" style="shape=archimate3.application;fillColor=#4A90D9;strokeColor=#333333;" vertex="1" parent="1">
      <mxGeometry x="300" y="200" width="100" height="100" as="geometry"/>
    </mxCell>
  </root>
</mxGraphModel>"""


@pytest.fixture
def valid_xml_with_disallowed_color() -> str:
    """Draw.io XML using a color outside the allowed palette."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<mxGraphModel>
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
    <mxCell id="2" value="Red Box" style="fillColor=#FF0000;strokeColor=#333333;" vertex="1" parent="1">
      <mxGeometry x="100" y="100" width="100" height="100" as="geometry"/>
    </mxCell>
  </root>
</mxGraphModel>"""


@pytest.fixture
def invalid_xml() -> str:
    """Malformed XML for testing error handling."""
    return """<mxGraphModel>
  <root>
    <mxCell id="0">
    <mxCell id="1" parent="0">
  </root>
</mxGraphBROKEN>"""


@pytest.fixture
def empty_xml() -> str:
    """Empty XML content."""
    return ""


# =============================================================================
# Mock Redis and ARQ
# =============================================================================


@pytest.fixture
def mock_redis():
    """Mock Redis connection."""
    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.enqueue_job = AsyncMock()
    redis_mock.close = AsyncMock()
    return redis_mock


@pytest.fixture
def mock_arq_pool():
    """Mock ARQ pool for task enqueuing."""
    pool = AsyncMock()
    pool.ping = AsyncMock(return_value=True)

    mock_job = MagicMock()
    mock_job.job_id = str(uuid.uuid4())

    async def mock_enqueue(*args: object, **kwargs: object) -> MagicMock:
        return mock_job

    pool.enqueue_job = mock_enqueue
    pool.get_job_result = AsyncMock(return_value=None)
    pool.close = AsyncMock()
    return pool


# =============================================================================
# Mock Settings
# =============================================================================


@pytest.fixture
def test_settings_dict() -> dict:
    """Provide test settings for config override."""
    return {
        "ALLOWED_STENCILS": "aws4,gcp2,azure,archimate3,c4,cisco,oci",
        "ALLOWED_COLORS": "4A90D9,333333,1A1A1A,50C878,FFFFFF",
        "ARCHIMATE_LICENSE_KEY": "",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": 6379,
        "S3_BUCKET_NAME": "test-bucket",
        "DRAWIO_CLI_PATH": "/usr/bin/echo",
    }


# =============================================================================
# Auto-use fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _disable_network(monkeypatch):
    """Prevent tests from making real network calls."""
    import httpx

    async def mock_get(*args, **kwargs):
        raise RuntimeError("Test attempted real HTTP request — use mock instead")

    def mock_init(*args, **kwargs):
        pass

    monkeypatch.setattr(httpx.AsyncClient, "__init__", mock_init)


@pytest.fixture(autouse=True)
def _mock_boto3(monkeypatch):
    """Prevent boto3 from making real AWS calls."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://localhost:9000")