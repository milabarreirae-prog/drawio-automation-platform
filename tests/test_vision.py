"""
Tests del módulo de visión: extracción de nivel desde prompt y VisionExtractor.
"""

from __future__ import annotations

import base64
from unittest.mock import patch

import pytest

from c4norm.vision import VisionExtractor, extract_level_from_prompt

# 1×1 PNG mínimo válido
_PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
    b'\x00\x01\x01\x00\x05\x18\xd5\xd3\x00\x00\x00\x00IEND\xaeB`\x82'
)

_FAKE_XML = """<mxGraphModel><root>
  <mxCell id="0"/><mxCell id="1" parent="0"/>
  <mxCell id="n1" value="Portabilidad Mongo ATLAS" style="shape=cylinder" vertex="1" parent="1">
    <mxGeometry x="100" y="100" width="120" height="80" as="geometry"/>
  </mxCell>
  <mxCell id="n2" value="Kafka Connect Source" style="rounded=1;" vertex="1" parent="1">
    <mxGeometry x="300" y="100" width="160" height="60" as="geometry"/>
  </mxCell>
  <mxCell id="e1" value="(*) Connector Errors" edge="1" source="n1" target="n2" parent="1">
    <mxGeometry relative="1" as="geometry"/>
  </mxCell>
</root></mxGraphModel>"""


# =============================================================================
# extract_level_from_prompt
# =============================================================================

@pytest.mark.parametrize("text,expected", [
    # Formato c4nX
    ("hola reiiiina del pop, como podria hacer un diagrama c4n1 con esta info?", 1),
    ("quiero c4n2", 2),
    ("dame C4 N 3", 3),
    ("C4N1 por favor", 1),
    # nivel / level
    ("necesito nivel 1", 1),
    ("level 2 diagram", 2),
    ("nivel1", 1),
    # Palabras clave semánticas
    ("diagrama de contexto", 1),
    ("vista de contenedores", 2),
    ("descomponer en componentes", 3),
    # Sin pista → 2
    ("hola wattsha como andamios", 2),
    ("sin ninguna pista", 2),
])
def test_extract_level_from_prompt(text: str, expected: int) -> None:
    assert extract_level_from_prompt(text) == expected


# =============================================================================
# VisionExtractor (con chat inyectado — sin red)
# =============================================================================

def test_extractor_returns_xml() -> None:
    received: dict = {}

    def fake_chat(img: bytes, prompt: str) -> str:
        received["img"] = img
        received["prompt"] = prompt
        return _FAKE_XML

    xml = VisionExtractor(chat=fake_chat).extract(_PNG, prompt="c4n1")
    assert "<mxGraphModel" in xml
    assert received["img"] == _PNG
    assert "c4n1" in received["prompt"]


def test_extractor_strips_markdown_fences() -> None:
    def fake_chat(img: bytes, prompt: str) -> str:
        return f"```xml\n{_FAKE_XML}\n```"

    xml = VisionExtractor(chat=fake_chat).extract(_PNG)
    assert xml.startswith("<mxGraphModel")


def test_extractor_strips_plain_fences() -> None:
    def fake_chat(img: bytes, prompt: str) -> str:
        return f"```\n{_FAKE_XML}\n```"

    xml = VisionExtractor(chat=fake_chat).extract(_PNG)
    assert xml.startswith("<mxGraphModel")


def test_extractor_retries_on_invalid_then_succeeds() -> None:
    calls = {"n": 0}

    def flaky_chat(img: bytes, prompt: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "esto no es xml"
        return _FAKE_XML

    xml = VisionExtractor(chat=flaky_chat, retries=2).extract(_PNG)
    assert calls["n"] == 2
    assert "<mxCell" in xml


def test_extractor_raises_after_all_retries() -> None:
    with pytest.raises(ValueError, match="inválida tras"):
        VisionExtractor(chat=lambda _b, _p: "not xml", retries=1).extract(_PNG)


def test_extractor_requires_key_without_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("C4NORM_LLM_API_KEY", raising=False)
    with pytest.raises(ValueError, match="C4NORM_LLM_API_KEY"):
        VisionExtractor().extract(_PNG)


# =============================================================================
# Normalización end-to-end con XML inyectado (vision → c4norm pipeline)
# =============================================================================

def test_vision_xml_feeds_normalizer() -> None:
    """El XML producido por el LLM de visión pasa correctamente por c4norm.normalize()."""
    from c4norm.normalize import normalize

    xml_c4, report = normalize(_FAKE_XML, c4_level=1)
    assert "<mxfile" in xml_c4
    assert report.node_count >= 1


# =============================================================================
# API endpoint /from-image (con VisionExtractor mockeado)
# =============================================================================

def test_api_from_image_extracts_level_from_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from api.config import Settings
    from api.main import _clear_rate_limit_state, app

    _clear_rate_limit_state()
    img_b64 = base64.b64encode(_PNG).decode()

    with patch("api.main.VisionExtractor") as mock_vision:
        mock_vision.return_value.extract.return_value = _FAKE_XML
        with patch("api.main.settings", Settings(
            c4norm_llm_api_key="test-key",
            c4norm_vision_model="qwen3.6-plus",
        )):
            client = TestClient(app)
            response = client.post(
                "/api/v1/diagram/from-image",
                json={
                    "image_base64": img_b64,
                    "prompt": "hola reiiiina del pop, como podria hacer un diagrama c4n1 con esta info?",
                },
            )
    assert response.status_code == 200
    data = response.json()
    assert data["report"]["c4_level"] == 1   # extraído del prompt "c4n1"
    assert "xml_c4" in data
    assert data["report"]["node_count"] >= 1


def test_api_from_image_explicit_level_overrides_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from api.config import Settings
    from api.main import _clear_rate_limit_state, app

    _clear_rate_limit_state()
    img_b64 = base64.b64encode(_PNG).decode()

    with patch("api.main.VisionExtractor") as mock_vision:
        mock_vision.return_value.extract.return_value = _FAKE_XML
        with patch("api.main.settings", Settings(
            c4norm_llm_api_key="test-key",
            c4norm_vision_model="qwen3.6-plus",
        )):
            client = TestClient(app)
            response = client.post(
                "/api/v1/diagram/from-image",
                json={"image_base64": img_b64, "prompt": "c4n1", "c4_level": 3},
            )
    assert response.status_code == 200
    assert response.json()["report"]["c4_level"] == 3  # campo explícito prevalece


def test_api_from_image_503_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from api.config import Settings
    from api.main import _clear_rate_limit_state, app

    _clear_rate_limit_state()
    with patch("api.main.settings", Settings(c4norm_llm_api_key="")):
        client = TestClient(app)
        response = client.post(
            "/api/v1/diagram/from-image",
            json={"image_base64": base64.b64encode(_PNG).decode()},
        )
    assert response.status_code == 503


def test_api_from_image_422_invalid_b64() -> None:
    from fastapi.testclient import TestClient

    from api.config import Settings
    from api.main import _clear_rate_limit_state, app

    _clear_rate_limit_state()
    with patch("api.main.settings", Settings(c4norm_llm_api_key="test-key")):
        client = TestClient(app)
        response = client.post(
            "/api/v1/diagram/from-image",
            json={"image_base64": "!!!notbase64!!!"},
        )
    assert response.status_code == 422
