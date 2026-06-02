"""
Tests de multi-hoja: descomposición por boundary cuando el diagrama desborda.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

import c4norm.emit as emit_mod
from c4norm.emit import _decompose, emit_c4
from c4norm.model import C4Type, Diagram, Edge, Node

if TYPE_CHECKING:
    import pytest


def _multisite() -> Diagram:
    return Diagram(
        name="Despliegue",
        nodes=[
            Node(id="user", c4_type=C4Type.PERSON, c4_name="Usuario"),
            Node(id="siteA", c4_type=C4Type.DEPLOYMENT_NODE, c4_name="Sitio A"),
            Node(id="a1", c4_type=C4Type.CONTAINER, c4_name="API A", parent="siteA"),
            Node(id="a2", c4_type=C4Type.CONTAINER, c4_name="DB A", parent="siteA"),
            Node(id="siteB", c4_type=C4Type.DEPLOYMENT_NODE, c4_name="Sitio B"),
            Node(id="b1", c4_type=C4Type.CONTAINER, c4_name="API B", parent="siteB"),
        ],
        edges=[
            Edge(id="e1", source="user", target="a1"),  # Contexto -> A (cruza)
            Edge(id="e2", source="a1", target="a2"),  # intra A (se dibuja)
            Edge(id="e3", source="a1", target="b1"),  # A -> B (cruza)
        ],
    )


def test_decompose_splits_by_boundary_and_context() -> None:
    pages = _decompose(_multisite())
    titles = [t for t, _ in pages]
    assert titles == ["Contexto", "Sitio A", "Sitio B"]
    assert {n.id for n in pages[0][1].nodes} == {"user"}
    assert {n.id for n in pages[1][1].nodes} == {"siteA", "a1", "a2"}
    assert {n.id for n in pages[2][1].nodes} == {"siteB", "b1"}


def test_multisheet_when_overflow(monkeypatch: pytest.MonkeyPatch) -> None:
    # Forzar "desborde" subiendo el umbral mínimo de escala.
    monkeypatch.setattr(emit_mod, "_MIN_SCALE", 5.0)
    result = emit_c4(_multisite(), c4_level=2)
    assert result.sheets == 3
    root = etree.fromstring(result.xml.encode("utf-8"))
    assert root.tag == "mxfile"
    assert len(root.findall("diagram")) == 3
    # e1 (Contexto->A) y e3 (A->B) cruzan hojas; e2 (intra A) se dibuja.
    assert result.cross_sheet_edges == 2


def test_single_sheet_when_fits() -> None:
    result = emit_c4(_multisite(), c4_level=2)
    assert result.sheets == 1
    assert result.cross_sheet_edges == 0
    root = etree.fromstring(result.xml.encode("utf-8"))
    assert len(root.findall("diagram")) == 1


def test_no_split_without_two_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(emit_mod, "_MIN_SCALE", 5.0)
    d = Diagram(
        name="uno",
        nodes=[
            Node(id="s", c4_type=C4Type.DEPLOYMENT_NODE, c4_name="Sitio"),
            Node(id="c", c4_type=C4Type.CONTAINER, c4_name="C", parent="s"),
        ],
    )
    result = emit_c4(d, c4_level=2)
    assert result.sheets == 1  # un solo boundary: no hay por qué descomponer
    assert result.overflow is True  # pero sí está marcado como desbordado
