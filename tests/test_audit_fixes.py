"""
Tests para las correcciones de la auditoría de código:
  - Fix 1: dashed=0 en relaciones C4 (conformidad oficial)
  - Fix 2: nivel 3 → Component (no Container)
  - Fix 3: LRUCache en rate-limit + IP truncada
  - Bonus: API key en tiempo constante (hmac.compare_digest)
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from c4norm.classify import HeuristicClassifier
from c4norm.model import RELATIONSHIP_STYLE, C4Type
from c4norm.normalize import normalize
from c4norm.parse import parse_drawio

# XML mínimo con dos nodos genéricos para testear clasificación
_XML_TWO_BOXES = """<mxGraphModel>
  <root>
    <mxCell id="0"/><mxCell id="1" parent="0"/>
    <mxCell id="a" value="Servicio A" style="rounded=1;" vertex="1" parent="1">
      <mxGeometry x="0" y="0" width="120" height="60" as="geometry"/>
    </mxCell>
    <mxCell id="b" value="Servicio B" style="rounded=1;" vertex="1" parent="1">
      <mxGeometry x="200" y="0" width="120" height="60" as="geometry"/>
    </mxCell>
    <mxCell id="e1" edge="1" source="a" target="b" parent="1">
      <mxGeometry relative="1" as="geometry"/>
    </mxCell>
  </root>
</mxGraphModel>"""


# =============================================================================
# Fix 1 — dashed=0 en relaciones (conformidad C4 oficial)
# =============================================================================

def test_relationship_style_is_not_dashed() -> None:
    """La plantilla oficial C4 usa dashed=0, no dashed=1 (convención ArchiMate)."""
    assert "dashed=0" in RELATIONSHIP_STYLE
    assert "dashed=1" not in RELATIONSHIP_STYLE


def test_emitted_xml_relationships_are_solid() -> None:
    """Los edges emitidos deben tener dashed=0 (el style va antes de edge= en el XML)."""
    import re
    xml_c4, _ = normalize(_XML_TWO_BOXES, c4_level=2)
    # El emit genera: <mxCell style="..." ... edge="1">
    # Extraer style de todos los mxCell que también tengan edge="1" en el mismo bloque
    edge_styles = re.findall(r'<mxCell\s+style="([^"]*)"[^>]*\bedge="1"', xml_c4)
    assert edge_styles, "No se encontraron aristas en el XML emitido"
    for style in edge_styles:
        assert "dashed=0" in style, f"Arista con dashed incorrecto: {style[:80]}"
        assert "dashed=1" not in style


# =============================================================================
# Fix 2 — nivel 3 → Component (no Container)
# =============================================================================

def test_level3_generic_box_classified_as_component() -> None:
    """Nivel C4=3: cajas genéricas deben ser Component, no Container."""
    diagram = parse_drawio(_XML_TWO_BOXES)[0]
    HeuristicClassifier().classify(diagram, c4_level=3)
    for node in diagram.nodes:
        assert node.c4_type is C4Type.COMPONENT, (
            f"Nodo '{node.id}' clasificado como {node.c4_type} en nivel 3, esperado Component"
        )


def test_level2_generic_box_classified_as_container() -> None:
    """Nivel C4=2: cajas genéricas siguen siendo Container."""
    diagram = parse_drawio(_XML_TWO_BOXES)[0]
    HeuristicClassifier().classify(diagram, c4_level=2)
    for node in diagram.nodes:
        assert node.c4_type is C4Type.CONTAINER


def test_level1_generic_box_classified_as_software_system() -> None:
    """Nivel C4=1: cajas genéricas son Software System."""
    diagram = parse_drawio(_XML_TWO_BOXES)[0]
    HeuristicClassifier().classify(diagram, c4_level=1)
    for node in diagram.nodes:
        assert node.c4_type is C4Type.SOFTWARE_SYSTEM


def test_level3_emits_component_style() -> None:
    """El XML emitido en nivel 3 debe contener el color canónico de Component (#85BBF0)."""
    xml_c4, report = normalize(_XML_TWO_BOXES, c4_level=3)
    assert "Component" in report.type_histogram, f"Histograma: {report.type_histogram}"
    assert "#85BBF0" in xml_c4, "Color canónico de Component (#85BBF0) ausente en el XML"
    # No debe haber el azul de Container si todas las cajas son genéricas
    assert "Container" not in report.type_histogram


# =============================================================================
# Fix 3 — LRUCache + IP truncada
# =============================================================================

def test_rate_limit_uses_lrucache() -> None:
    """_rate_limit_events debe ser LRUCache, no defaultdict ilimitado."""
    from cachetools import LRUCache

    import api.main as m
    assert isinstance(m._rate_limit_events, LRUCache), (
        f"_rate_limit_events es {type(m._rate_limit_events).__name__}, esperado LRUCache"
    )
    assert m._rate_limit_events.maxsize == 50_000


def test_client_ip_truncated_to_45_chars() -> None:
    """IPs largas (potencial ataque) se truncan a 45 chars."""
    from unittest.mock import MagicMock

    from api.main import _client_ip

    request = MagicMock()
    long_ip = "A" * 200
    request.headers.get.return_value = long_ip
    request.client = None
    ip = _client_ip(request)
    assert len(ip) == 45
    assert ip == "A" * 45


def test_rate_limit_different_ips_dont_share_buckets() -> None:
    """Clientes con IPs distintas tienen buckets separados."""
    from api.config import Settings
    from api.main import _clear_rate_limit_state

    _clear_rate_limit_state()
    with patch("api.main.settings", Settings(rate_limit_normalize_per_minute=1)):
        client = TestClient(__import__("api.main", fromlist=["app"]).app)
        # IP 1: primera request OK
        r1 = client.post(
            "/api/v1/diagram/normalize",
            json={"xml_content": _XML_TWO_BOXES},
            headers={"X-Forwarded-For": "1.2.3.4"},
        )
        # IP 2: también OK (bucket distinto)
        r2 = client.post(
            "/api/v1/diagram/normalize",
            json={"xml_content": _XML_TWO_BOXES},
            headers={"X-Forwarded-For": "5.6.7.8"},
        )
    assert r1.status_code == 200
    assert r2.status_code == 200


# =============================================================================
# Bonus — API key en tiempo constante (hmac.compare_digest)
# =============================================================================

def test_api_key_uses_constant_time_comparison() -> None:
    """_enforce_api_key usa hmac.compare_digest, no ==."""
    import inspect

    import api.main as m
    src = inspect.getsource(m._enforce_api_key)
    assert "hmac.compare_digest" in src, (
        "_enforce_api_key debe usar hmac.compare_digest para evitar timing attacks"
    )
    assert " == " not in src or "settings.api_key" not in src.split("compare_digest")[1]
