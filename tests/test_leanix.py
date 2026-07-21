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

from c4norm.leanix import (
    LEANIX_C4_MAP,
    LeanIXClient,
    inventory_to_diagram,
    leanix_to_c4,
    parse_factsheets,
)
from c4norm.model import C4Type

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "leanix_falabella.json"


def _load_fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


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
