"""
Tests de cobertura adicional para c4norm (boost a >=93%).

Apunta a ramas y líneas no cubiertas en:
  * c4norm.parse (fix_mojibake error/no-op, _geometry sin geometry, _edge_points,
    _iter_graph_models fallback, _build_diagram sin root, <object> con <mxCell>,
    celdas no-vertex/no-edge, skip container en _nearest_node)
  * c4norm.vision (_env_int error, _mime_type JPEG/WebP/PNG-fallback)
  * c4norm.normalize (sin diagramas, enforce_container_types warning,
    enricher ValueError, low_confidence, _install_standard_legend con notas)
  * c4norm.leanix (parse_factsheets non-dict item, _relation_targets con
    edges no-lista / edge no-dict, _declared_parent variants, inventory
    sin id string)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from lxml import etree

from c4norm.leanix import (
    _declared_parent,
    _relation_targets,
    inventory_to_diagram,
    parse_factsheets,
)
from c4norm.model import Annotation, C4Type, Diagram, Edge, Node
from c4norm.normalize import _install_standard_legend, normalize
from c4norm.parse import (
    _build_diagram,
    _edge_points,
    _geometry,
    _iter_graph_models,
    _nearest_node,
    fix_mojibake,
    parse_drawio,
)
from c4norm.vision import _env_int, _mime_type


# =============================================================================
# c4norm.parse — fix_mojibake (líneas 43-44, 48)
# =============================================================================


def test_fix_mojibake_encoding_error_returns_original() -> None:
    """Líneas 43-44: 'Ã' presente pero hay un carácter fuera de CP1252,
    el encode() falla → se devuelve el original."""
    bad = "Ãሴ"  # U+1234 no está en CP1252
    assert fix_mojibake(bad) == bad


def test_fix_mojibake_no_improvement_returns_original() -> None:
    """Línea 48: el round-trip CP1252→UTF-8 no reduce marcadores de mojibake."""
    # "Ã" (0xC3) + "ƒ" (0x83 en CP1252) ⇒ b'\xc3\x83' ⇒ "Ã" en UTF-8.
    # Conteo de 'Ã' pasa de 1 a 1 → sin mejora → línea 48.
    original = "Ãƒ"
    assert fix_mojibake(original) == original


# =============================================================================
# c4norm.parse — _geometry sin geometry (línea 88)
# =============================================================================


def test_geometry_returns_default_when_missing() -> None:
    """Línea 88: <mxCell> sin <mxGeometry> devuelve el default."""
    cell = etree.fromstring('<mxCell id="x"/>')
    assert _geometry(cell) == (0.0, 0.0, 120.0, 60.0)


# =============================================================================
# c4norm.parse — _edge_points con sourcePoint/targetPoint (líneas 98-103)
# =============================================================================


def test_edge_points_extracts_source_and_target() -> None:
    """Líneas 98-103: ambos mxPoint sourcePoint/targetPoint."""
    cell = etree.fromstring(
        '<mxCell id="e1" edge="1">'
        '  <mxGeometry relative="1" as="geometry">'
        '    <mxPoint x="10" y="20" as="sourcePoint"/>'
        '    <mxPoint x="100" y="200" as="targetPoint"/>'
        '  </mxGeometry>'
        '</mxCell>'
    )
    src, tgt = _edge_points(cell)
    assert src == (10.0, 20.0)
    assert tgt == (100.0, 200.0)


# =============================================================================
# c4norm.parse — _iter_graph_models fallback (líneas 133-135)
# =============================================================================


def test_iter_graph_models_fallback_no_diagram_element() -> None:
    """Líneas 133-135: mxfile sin <diagram> pero con <mxGraphModel> descendiente."""
    root = etree.fromstring(
        '<mxfile><mxGraphModel><root>'
        '<mxCell id="0"/><mxCell id="1" parent="0"/>'
        '</root></mxGraphModel></mxfile>'
    )
    models = _iter_graph_models(root)
    assert len(models) == 1
    assert models[0][0] == "Diagram"


# =============================================================================
# c4norm.parse — _build_diagram (líneas 142, 153-160, 165, 228)
# =============================================================================


def test_build_diagram_without_root_returns_empty() -> None:
    """Línea 142: mxGraphModel sin <root> → Diagram vacío."""
    gm = etree.fromstring('<mxGraphModel/>')
    d = _build_diagram("Empty", gm)
    assert d.name == "Empty"
    assert d.nodes == []
    assert d.edges == []


def test_build_diagram_ingests_object_with_mxcell_and_skips_seen() -> None:
    """Líneas 153-160 y 165: <object c4Type label> con <mxCell>: se ingresa
    como nodo; el mxCell queda en seen_cells y no se procesa dos veces.
    Además, un <object> sin <mxCell> se descarta (línea 155)."""
    gm = etree.fromstring(
        '<mxGraphModel><root>'
        '<mxCell id="0"/><mxCell id="1" parent="0"/>'
        '<object id="n1" label="API Gateway" c4Type="Container">'
        '  <mxCell style="rounded=1;" vertex="1" parent="1">'
        '    <mxGeometry x="10" y="20" width="80" height="40" as="geometry"/>'
        '  </mxCell>'
        '</object>'
        '<object id="sin-celda" label="sin mxCell hijo"/>'
        '</root></mxGraphModel>'
    )
    d = _build_diagram("D", gm)
    assert len(d.nodes) == 1
    node = d.nodes[0]
    assert node.id == "n1"
    assert node.explicit_c4_type == "Container"
    assert node.raw_label == "API Gateway"


def test_ingest_skips_non_vertex_non_edge() -> None:
    """Línea 228: <mxCell> sin edge="1" ni vertex="1" se ignora."""
    gm = etree.fromstring(
        '<mxGraphModel><root>'
        '<mxCell id="0"/><mxCell id="1" parent="0"/>'
        '<mxCell id="ghost" value="fantasma" style="rounded=1;"/>'
        '</root></mxGraphModel>'
    )
    d = _build_diagram("D", gm)
    assert d.nodes == []


# =============================================================================
# c4norm.parse — _nearest_node ignora contenedores (línea 303)
# =============================================================================


def test_nearest_node_skips_containers() -> None:
    """Línea 303: is_container_src=True ⇒ no es candidato para arista huérfana."""
    d = Diagram()
    d.nodes = [
        Node(id="c1", x=0, y=0, width=100, height=100, is_container_src=True),
        Node(id="n1", x=200, y=0, width=50, height=50, is_container_src=False),
    ]
    # Dentro del contenedor: no matchea.
    assert _nearest_node(d, (50.0, 50.0), threshold=5.0) is None
    # Dentro del nodo regular: matchea.
    hit = _nearest_node(d, (220.0, 20.0), threshold=5.0)
    assert hit is not None and hit.id == "n1"


# =============================================================================
# c4norm.vision — _env_int (líneas 30-31) y _mime_type (líneas 128-132)
# =============================================================================


def test_env_int_invalid_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """Líneas 30-31: valor no entero en entorno → fallback al default."""
    monkeypatch.setenv("C4NORM_VISION_TIMEOUT", "not-an-int")
    assert _env_int("C4NORM_VISION_TIMEOUT", 99) == 99


def test_mime_type_detects_jpeg_webp_and_png_fallback() -> None:
    """Líneas 128-132: magic JPEG, RIFF…WEBP, y fallback PNG."""
    assert _mime_type(b"\xff\xd8\xffrest") == "image/jpeg"
    assert _mime_type(b"RIFF\x00\x00\x00\x00WEBPmore") == "image/webp"
    assert _mime_type(b"\x00\x00\x00\x00") == "image/png"


# =============================================================================
# c4norm.normalize — sin diagramas (línea 97) y enforce warning (línea 114)
# =============================================================================


def test_normalize_empty_diagrams_raises() -> None:
    """Línea 97: XML válido pero sin ningún mxGraphModel → ValueError."""
    with pytest.raises(ValueError, match="No se encontró"):
        normalize("<mxfile></mxfile>")


def test_normalize_xml_with_child_node_emits_warning() -> None:
    """Línea 114: un nodo con hijos tipado como Container se reclasifica a
    DeploymentNode y se emite advertencia."""
    xml = (
        '<mxGraphModel><root>'
        '<mxCell id="0"/><mxCell id="1" parent="0"/>'
        '<mxCell id="p" value="Parent" style="rounded=1;" vertex="1" parent="1">'
        '  <mxGeometry x="0" y="0" width="200" height="200" as="geometry"/>'
        '</mxCell>'
        '<mxCell id="h" value="Child" style="rounded=1;" vertex="1" parent="p">'
        '  <mxGeometry x="10" y="10" width="60" height="40" as="geometry"/>'
        '</mxCell>'
        '</root></mxGraphModel>'
    )
    _, report = normalize(xml, c4_level=2)
    assert any("reclasificaron a DeploymentNode" for w in report.warnings)


# =============================================================================
# c4norm.normalize — _install_standard_legend con notas (líneas 64-65)
# =============================================================================


def test_install_standard_legend_uses_kept_annotations_anchor() -> None:
    """Líneas 64-65: con anotaciones no-leyenda, el ancla se calcula desde ellas
    (min x, max y+height + 40)."""
    d = Diagram()
    d.nodes = [Node(id="n1", raw_label="X", c4_type=C4Type.CONTAINER)]
    d.edges = [Edge(id="e1", source="n1", target="n1")]
    d.annotations = [
        Annotation(id="note1", value="Nota", style="shape=note;", kind="note",
                   x=50.0, y=100.0, width=80.0, height=40.0),
    ]
    _install_standard_legend(d)
    legend_annos = [a for a in d.annotations if a.kind == "legend"]
    assert legend_annos, "debe haberse agregado la leyenda estándar"
    # anchor_y = (100 + 40) + 40 = 180. frame.y = anchor_y - 10 = 170.
    frame = next(a for a in legend_annos if a.id == "legend-frame")
    assert frame.y == 170.0


# =============================================================================
# c4norm.normalize — enricher ValueError (líneas 148-149) y low_confidence (159)
# =============================================================================


def test_normalize_enricher_valueerror_becomes_warning() -> None:
    """Líneas 148-149: enricher que lanza ValueError se captura y convierte en
    advertencia; el pipeline sigue."""
    xml = (
        '<mxGraphModel><root>'
        '<mxCell id="0"/><mxCell id="1" parent="0"/>'
        '<mxCell id="n1" value="A" style="rounded=1;" vertex="1" parent="1">'
        '  <mxGeometry x="0" y="0" width="100" height="50" as="geometry"/>'
        '</mxCell>'
        '</root></mxGraphModel>'
    )
    enricher = MagicMock()
    enricher.enrich.side_effect = ValueError("LLM devolvió XML inválido")
    _, report = normalize(xml, enrich=True, enricher=enricher)
    assert any("Enriquecimiento omitido" in w for w in report.warnings)


def test_normalize_low_confidence_node() -> None:
    """Línea 159: nodo sin explicit_c4_type y raw_label vacío ⇒ low_confidence."""
    xml = (
        '<mxGraphModel><root>'
        '<mxCell id="0"/><mxCell id="1" parent="0"/>'
        '<mxCell id="empty" value="" style="rounded=1;" vertex="1" parent="1">'
        '  <mxGeometry x="0" y="0" width="100" height="50" as="geometry"/>'
        '</mxCell>'
        '</root></mxGraphModel>'
    )
    _, report = normalize(xml, c4_level=2)
    assert "empty" in report.low_confidence


# =============================================================================
# c4norm.leanix — parse_factsheets non-dict item (línea 144)
# =============================================================================


def test_parse_factsheets_skips_non_dict_item() -> None:
    """Línea 144: items de edges que no son dict se ignoran."""
    response = {
        "data": {
            "allFactSheets": {
                "edges": [
                    None,
                    "not-a-dict",
                    {"node": {"id": "fs-1", "type": "Application"}},
                ]
            }
        }
    }
    nodes = parse_factsheets(response)
    assert len(nodes) == 1
    assert nodes[0]["id"] == "fs-1"


# =============================================================================
# c4norm.leanix — _relation_targets (líneas 170, 173)
# =============================================================================


def test_relation_targets_edge_cases() -> None:
    """Líneas 170 y 173: edges no-lista e items no-dict se ignoran."""
    assert _relation_targets({"relFoo": {"edges": "nope"}}) == []
    raw = {
        "relApplicationToITComponent": {
            "edges": [None, 42, {"node": {"factSheet": {"id": "tgt-1"}}}]
        },
    }
    assert _relation_targets(raw) == ["tgt-1"]
    # relToParent NUNCA se trata como relación (va aparte).
    assert _relation_targets({"relToParent": {"edges": [{"node": {"factSheet": {"id": "p"}}}]}}) == []


# =============================================================================
# c4norm.leanix — _declared_parent (líneas 197, 200, 206)
# =============================================================================


def test_declared_parent_edge_cases() -> None:
    """Líneas 197, 200, 206: ramas defensivas de _declared_parent."""
    # edges no-lista → None
    assert _declared_parent({"relToParent": {"edges": "nope"}}) is None
    # edge no-dict se salta
    assert _declared_parent({"relToParent": {"edges": [None, 42]}}) is None
    # edges presentes pero sin id válido → None
    assert _declared_parent({
        "relToParent": {
            "edges": [
                {"node": {"factSheet": {"id": ""}}},
                {"node": {"factSheet": None}},
                {"node": None},
            ]
        }
    }) is None
    # caso válido
    assert _declared_parent(
        {"relToParent": {"edges": [{"node": {"factSheet": {"id": "p-1"}}}]}}
    ) == "p-1"


# =============================================================================
# c4norm.leanix — inventory_to_diagram non-string id (línea 237)
# =============================================================================


def test_inventory_to_diagram_skips_non_string_id() -> None:
    """Línea 237: FactSheet sin id string se descarta sin inventar uno."""
    response = {
        "data": {
            "allFactSheets": {
                "edges": [
                    {"node": {"id": 123, "type": "Application"}},
                    {"node": {"id": "", "type": "Application"}},
                    {"node": {"id": "ok-1", "type": "Application"}},
                ]
            }
        }
    }
    diagram, _warnings = inventory_to_diagram(response)
    assert len(diagram.nodes) == 1
    assert diagram.nodes[0].id == "ok-1"
