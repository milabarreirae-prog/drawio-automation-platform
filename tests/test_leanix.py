"""
Tests del módulo de ingesta LeanIX (FactSheets ya tipados → Diagram C4 → XML).

Cubre: parseo defensivo de la respuesta GraphQL, mapeo determinista LeanIX→C4Type,
el invariante de fidelidad Ax-C4N-001 (tipo desconocido NUNCA se descarta, se marca
"por validar"), el descarte de relaciones colgantes, el camino end-to-end
``leanix_to_c4``, y el transporte inyectable de ``LeanIXClient``.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import c4norm.emit as emit_mod
from c4norm.leanix import (
    LEANIX_C4_MAP,
    LeanIXClient,
    inventory_to_diagram,
    leanix_to_c4,
    parse_factsheets,
)
from c4norm.model import C4Type

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "leanix_falabella.json"
_HIERARCHY_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "leanix_falabella_hierarchy.json"


def _load_fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _load_hierarchy_fixture() -> dict:
    return json.loads(_HIERARCHY_FIXTURE_PATH.read_text(encoding="utf-8"))


# =============================================================================
# parse_factsheets
# =============================================================================


def test_parse_factsheets_counts_all_nodes() -> None:
    nodes = parse_factsheets(_load_fixture())
    # 8 FactSheets en el fixture (incluye la Interface, que no es nodo C4 pero sí
    # un FactSheet en la respuesta cruda).
    assert len(nodes) == 8
    ids = {n["id"] for n in nodes}
    assert "app-portal" in ids
    assert "provider-gateway" in ids


def test_parse_factsheets_empty_response_no_crash() -> None:
    assert parse_factsheets({}) == []
    assert parse_factsheets({"data": {}}) == []
    assert parse_factsheets({"data": {"allFactSheets": {}}}) == []
    assert parse_factsheets({"data": {"allFactSheets": {"edges": None}}}) == []
    assert parse_factsheets({"data": {"allFactSheets": {"edges": [{"node": None}, {}]}}}) == []


# =============================================================================
# inventory_to_diagram — mapeo determinista
# =============================================================================


def test_inventory_to_diagram_maps_known_types() -> None:
    diagram, _warnings = inventory_to_diagram(_load_fixture())
    by_id = {n.id: n for n in diagram.nodes}

    assert by_id["app-portal"].c4_type is C4Type.SOFTWARE_SYSTEM
    assert by_id["app-portal"].external is False

    assert by_id["itc-runtime"].c4_type is C4Type.CONTAINER

    assert by_id["do-clientes"].c4_type is C4Type.DATABASE

    assert by_id["provider-gateway"].c4_type is C4Type.SOFTWARE_SYSTEM
    assert by_id["provider-gateway"].external is True


def test_leanix_c4_map_matches_spec() -> None:
    assert LEANIX_C4_MAP == {
        "Application": C4Type.SOFTWARE_SYSTEM,
        "ITComponent": C4Type.CONTAINER,
        "DataObject": C4Type.DATABASE,
        "BusinessCapability": C4Type.COMPONENT,
        "Provider": C4Type.SOFTWARE_SYSTEM,
    }


# =============================================================================
# Ax-C4N-001 — tipo desconocido: nunca se descarta, se marca "por validar"
# =============================================================================


def test_unknown_type_is_not_dropped_and_marked_for_validation() -> None:
    """Prueba de diente: un FactSheet con tipo sin mapeo DEBE seguir existiendo como
    Node (nunca se calla silenciosamente), tipado neutro SOFTWARE_SYSTEM, y marcado
    "por validar" con confianza Baja + advertencia legible."""
    diagram, warnings = inventory_to_diagram(_load_fixture())
    by_id = {n.id: n for n in diagram.nodes}

    assert "techstack-legado" in by_id, "el nodo de tipo desconocido fue descartado silenciosamente"
    node = by_id["techstack-legado"]
    assert node.c4_type is C4Type.SOFTWARE_SYSTEM
    assert node.cmdb_status == "por validar"
    assert node.confidence == "Baja"

    assert any(
        "techstack-legado" in w and "TechnologyStack" in w and "por validar" in w for w in warnings
    ), f"falta advertencia por validar para tipo desconocido: {warnings}"


def test_interface_type_is_not_a_node_and_no_warning() -> None:
    """'Interface' representa una relación, no un nodo: se excluye SIN advertencia
    (caso conocido, distinto de un tipo verdaderamente desconocido)."""
    diagram, warnings = inventory_to_diagram(_load_fixture())
    ids = {n.id for n in diagram.nodes}
    assert "iface-portal-pagos" not in ids
    assert not any("iface-portal-pagos" in w for w in warnings)


# =============================================================================
# Relaciones — nunca colgar
# =============================================================================


def test_dangling_relationship_is_discarded_with_warning() -> None:
    diagram, warnings = inventory_to_diagram(_load_fixture())
    edge_pairs = {(e.source, e.target) for e in diagram.edges}

    assert ("app-portal", "do-inexistente") not in edge_pairs
    assert any(
        "app-portal->do-inexistente" in w and "descarta" in w for w in warnings
    ), f"falta advertencia de relación colgante: {warnings}"


def test_valid_relationships_are_kept() -> None:
    diagram, _warnings = inventory_to_diagram(_load_fixture())
    edge_pairs = {(e.source, e.target) for e in diagram.edges}

    assert ("app-portal", "itc-runtime") in edge_pairs
    assert ("app-portal", "do-clientes") in edge_pairs
    assert ("app-portal", "app-pagos") in edge_pairs
    assert ("app-pagos", "do-transacciones") in edge_pairs
    assert ("app-pagos", "provider-gateway") in edge_pairs


# =============================================================================
# Jerarquía declarada (relToParent) — Ax-C4N-001: agrupación SÓLO declarada
# =============================================================================


def test_no_hierarchy_stays_flat_and_unchanged() -> None:
    """Regresión: sin ningún ``relToParent`` en la respuesta, el comportamiento debe
    ser byte-idéntico al de hoy (todos los nodos sin parent, ningún boundary)."""
    diagram, warnings = inventory_to_diagram(_load_fixture())

    assert all(n.parent is None for n in diagram.nodes)
    assert all(n.c4_type is not C4Type.DEPLOYMENT_NODE for n in diagram.nodes)
    assert not any("promovido a boundary" in w for w in warnings)
    assert not any("declara parent" in w for w in warnings)


def test_declared_parent_is_assigned() -> None:
    diagram, _warnings = inventory_to_diagram(_load_hierarchy_fixture())
    by_id = {n.id: n for n in diagram.nodes}

    assert by_id["app-portal-h"].parent == "dc-region-a"
    assert by_id["app-pagos-h"].parent == "dc-region-a"
    assert by_id["app-reportes-h"].parent == "dc-region-b"


def test_rel_to_parent_does_not_produce_a_spurious_edge() -> None:
    """``relToParent`` empieza con ``rel`` pero es contención, no una relación de
    arquitectura: NUNCA debe aparecer como Edge padre→hijo."""
    diagram, _warnings = inventory_to_diagram(_load_hierarchy_fixture())
    edge_pairs = {(e.source, e.target) for e in diagram.edges}

    assert ("dc-region-a", "app-portal-h") not in edge_pairs
    assert ("app-portal-h", "dc-region-a") not in edge_pairs


def test_hierarchy_decomposes_into_multiple_sheets_when_forced_to_split(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``emit.py`` sólo decide multi-hoja cuando el contenido desborda la escala
    mínima; con la página ajustada 1:1 al contenido (``fit_page``) eso NUNCA ocurre
    por tamaño de contenido solo — el multi-hoja es condicional en escala, no
    automático por boundaries. Aquí se fuerza el umbral (mismo patrón que
    ``tests/test_multisheet.py::test_multisheet_when_overflow``) para probar por el
    camino REAL de ``emit_c4`` que la jerarquía declarada (padre → ``Node.parent`` →
    promoción a boundary) sí produce >1 hoja cuando ``emit.py`` decide dividir."""
    monkeypatch.setattr(emit_mod, "_MIN_SCALE", 5.0)
    diagram, _warnings = inventory_to_diagram(_load_hierarchy_fixture())
    result = emit_mod.emit_c4(diagram, c4_level=1)

    assert result.sheets > 1
    root = ET.fromstring(result.xml)  # noqa: S314 - XML propio, no de fuente externa
    assert len(root.findall("diagram")) > 1


def test_dangling_declared_parent_warns_and_does_not_group() -> None:
    diagram, warnings = inventory_to_diagram(_load_hierarchy_fixture())
    by_id = {n.id: n for n in diagram.nodes}

    assert "app-huerfano-h" in by_id, "el nodo con padre colgante fue descartado (nunca perder)"
    assert by_id["app-huerfano-h"].parent is None
    assert any(
        "app-huerfano-h" in w and "dc-region-inexistente" in w and "sin agrupar" in w for w in warnings
    ), f"falta advertencia de parent declarado inexistente: {warnings}"


def test_self_parent_is_ignored_without_cycle() -> None:
    diagram, warnings = inventory_to_diagram(_load_hierarchy_fixture())
    by_id = {n.id: n for n in diagram.nodes}

    assert by_id["app-selfparent-h"].parent is None
    assert any(
        "app-selfparent-h" in w and "a si mismo" in w and "ignorado" in w for w in warnings
    ), f"falta advertencia de self-parent: {warnings}"


def test_declared_parents_are_promoted_to_boundary_with_warning() -> None:
    diagram, warnings = inventory_to_diagram(_load_hierarchy_fixture())
    by_id = {n.id: n for n in diagram.nodes}

    assert by_id["dc-region-a"].c4_type is C4Type.DEPLOYMENT_NODE
    assert by_id["dc-region-b"].c4_type is C4Type.DEPLOYMENT_NODE
    # itc-shared-h no es padre de nadie: no se promueve.
    assert by_id["itc-shared-h"].c4_type is not C4Type.DEPLOYMENT_NODE

    assert any(
        "dc-region-a" in w and "promovido a boundary" in w and "2 hijos declarados" in w for w in warnings
    ), f"falta advertencia de promoción para dc-region-a: {warnings}"
    assert any(
        "dc-region-b" in w and "promovido a boundary" in w and "1 hijos declarados" in w for w in warnings
    ), f"falta advertencia de promoción para dc-region-b: {warnings}"


def test_hierarchy_end_to_end_produces_valid_xml() -> None:
    """Camino real vía ``emit_c4`` (mismo patrón que el end-to-end existente):
    una jerarquía declarada produce XML válido. Multi-hoja es condicional en escala
    (no automática por boundaries); eso es una futura palanca, no parte de B-04
    (Ax-C4N-023: «lo dudoso no bloquea, se marca»)."""
    xml_out, warnings = leanix_to_c4(
        _load_hierarchy_fixture(), c4_level=1, name="Inventario jerárquico (sintético)"
    )

    ET.fromstring(xml_out)  # noqa: S314 - XML propio, no de fuente externa
    # XML es válido; no aseveramos sobre sheet count (condicional en escala + desborde).

    assert any("promovido a boundary" in w for w in warnings)
    assert any("sin agrupar" in w for w in warnings)
    assert any("a si mismo" in w for w in warnings)


# =============================================================================
# leanix_to_c4 — end-to-end
# =============================================================================


def test_leanix_to_c4_end_to_end_produces_parseable_xml() -> None:
    xml_out, warnings = leanix_to_c4(_load_fixture(), c4_level=1, name="Inventario Falabella (sintético)")

    assert "<mxGraphModel" in xml_out or "<mxfile" in xml_out
    for expected_name in ("Portal Ventas", "Motor Pagos", "Gateway Pagos Externo", "BD Clientes"):
        assert expected_name in xml_out

    # Debe ser XML bien formado.
    ET.fromstring(xml_out)  # noqa: S314 - XML propio, no de fuente externa

    assert len(warnings) == 2  # 1 tipo desconocido + 1 relación colgante


# =============================================================================
# LeanIXClient — transporte inyectable
# =============================================================================


def test_leanix_client_without_token_or_post_raises() -> None:
    client = LeanIXClient(base_url="https://example.leanix.net", token="")
    with pytest.raises(ValueError, match="SSO federado"):
        client.fetch_inventory("query {}")


def test_leanix_client_with_injected_post_returns_fixture() -> None:
    fixture = _load_fixture()
    received: dict = {}

    def fake_post(query: str) -> dict:
        received["query"] = query
        return fixture

    client = LeanIXClient(post=fake_post)
    result = client.fetch_inventory("query AllFactSheets { allFactSheets { edges { node { id } } } }")

    assert result == fixture
    assert "AllFactSheets" in received["query"]
