"""
Tests del módulo de generación desde texto (TextExtractor) y del endpoint /from-text,
más el soporte de nivel C4=4 (código).
"""

from __future__ import annotations

import base64  # noqa: F401  (consistencia con otros tests de API)
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from c4norm.textgen import TextExtractor

_FAKE_XML = """<mxGraphModel><root>
  <mxCell id="0"/><mxCell id="1" parent="0"/>
  <mxCell id="api" value="API FastAPI" style="rounded=1;" vertex="1" parent="1">
    <mxGeometry x="0" y="0" width="160" height="60" as="geometry"/>
  </mxCell>
  <mxCell id="eng" value="Motor c4norm" style="rounded=1;" vertex="1" parent="1">
    <mxGeometry x="0" y="120" width="160" height="60" as="geometry"/>
  </mxCell>
  <mxCell id="e1" value="invoca" edge="1" source="api" target="eng" parent="1">
    <mxGeometry relative="1" as="geometry"/>
  </mxCell>
</root></mxGraphModel>"""

_DESC = "Una API FastAPI que invoca un motor c4norm para normalizar diagramas."


# =============================================================================
# TextExtractor (chat inyectado, sin red)
# =============================================================================

def test_textextractor_generates_xml() -> None:
    received = {}

    def fake_chat(prompt: str) -> str:
        received["prompt"] = prompt
        return _FAKE_XML

    xml = TextExtractor(chat=fake_chat).generate(_DESC, c4_level=2)
    assert "<mxGraphModel" in xml
    assert _DESC in received["prompt"]
    assert "nivel 2" in received["prompt"]


def test_textextractor_strips_fences() -> None:
    xml = TextExtractor(chat=lambda _p: f"```xml\n{_FAKE_XML}\n```").generate(_DESC)
    assert xml.startswith("<mxGraphModel")


def test_textextractor_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def flaky(prompt: str) -> str:
        calls["n"] += 1
        return "no es xml" if calls["n"] == 1 else _FAKE_XML

    xml = TextExtractor(chat=flaky, retries=2).generate(_DESC)
    assert calls["n"] == 2
    assert "<mxCell" in xml


def test_textextractor_empty_description_raises() -> None:
    with pytest.raises(ValueError, match="vac[ií]a"):
        TextExtractor(chat=lambda _p: _FAKE_XML).generate("   ")


def test_textextractor_requires_key_without_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("C4NORM_LLM_API_KEY", raising=False)
    with pytest.raises(ValueError, match="C4NORM_LLM_API_KEY"):
        TextExtractor().generate(_DESC)


def test_textextractor_passes_level_to_prompt() -> None:
    received = {}
    TextExtractor(chat=lambda p: received.update(prompt=p) or _FAKE_XML).generate(_DESC, c4_level=4)
    assert "nivel 4" in received["prompt"]


# =============================================================================
# Nivel C4 = 4 (código)
# =============================================================================

def test_extract_level_4_from_prompt() -> None:
    from c4norm.vision import extract_level_from_prompt

    assert extract_level_from_prompt("quiero un c4 n4") == 4
    assert extract_level_from_prompt("nivel 4 por favor") == 4
    assert extract_level_from_prompt("diagrama a nivel de código") == 4
    assert extract_level_from_prompt("vista de code") == 4


def test_normalize_accepts_level_4() -> None:
    from c4norm.normalize import normalize

    raw = "<mxGraphModel><root><mxCell id='0'/><mxCell id='1' parent='0'/><mxCell id='a' value='Modulo' vertex='1' parent='1'><mxGeometry x='0' y='0' width='120' height='60' as='geometry'/></mxCell></root></mxGraphModel>"
    xml_c4, report = normalize(raw, c4_level=4)
    assert report.c4_level == 4
    assert "C4 N4" in xml_c4


# =============================================================================
# Endpoint /from-text (TextExtractor mockeado)
# =============================================================================

def test_api_from_text_generates_diagram() -> None:
    from api.config import Settings
    from api.main import _clear_rate_limit_state, app

    _clear_rate_limit_state()
    with patch("api.main.TextExtractor") as mock_text:
        mock_text.return_value.generate.return_value = _FAKE_XML
        with patch("api.main.settings", Settings(c4norm_llm_api_key="test-key")):
            client = TestClient(app)
            r = client.post(
                "/api/v1/diagram/from-text",
                json={"description": _DESC, "c4_level": 4},
            )
    assert r.status_code == 200
    data = r.json()
    assert data["report"]["c4_level"] == 4
    assert data["report"]["node_count"] >= 1
    assert "<mxfile" in data["xml_c4"]


def test_api_from_text_503_without_key() -> None:
    from api.config import Settings
    from api.main import _clear_rate_limit_state, app

    _clear_rate_limit_state()
    with patch("api.main.settings", Settings(c4norm_llm_api_key="")):
        client = TestClient(app)
        r = client.post("/api/v1/diagram/from-text", json={"description": _DESC})
    assert r.status_code == 503


def test_api_from_text_422_empty_description() -> None:
    from api.config import Settings
    from api.main import _clear_rate_limit_state, app

    _clear_rate_limit_state()
    with patch("api.main.settings", Settings(c4norm_llm_api_key="test-key")):
        client = TestClient(app)
        r = client.post("/api/v1/diagram/from-text", json={"description": ""})
    assert r.status_code == 422  # min_length=1
