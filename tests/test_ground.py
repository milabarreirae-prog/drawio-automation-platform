"""
Tests del anclaje de nodos flotantes (`ground_floating_nodes`).
"""

from __future__ import annotations

from c4norm.ground import ground_floating_nodes
from c4norm.model import C4Type, Diagram, Node


def _node(nid: str, t: C4Type, parent: str | None = None) -> Node:
    return Node(id=nid, c4_type=t, parent=parent)


def test_grounds_all_infra_types_under_zone() -> None:
    d = Diagram(
        nodes=[
            _node("site", C4Type.DEPLOYMENT_NODE),
            _node("c", C4Type.CONTAINER),
            _node("db", C4Type.DATABASE),
            _node("comp", C4Type.COMPONENT),
        ]
    )
    grounded = ground_floating_nodes(d)
    assert grounded == 3
    zone = d.node_by_id("c4norm-conectividad")
    assert zone is not None
    assert zone.c4_type is C4Type.DEPLOYMENT_NODE
    for nid in ("c", "db", "comp"):
        assert d.node_by_id(nid).parent == "c4norm-conectividad"


def test_no_boundary_no_grounding() -> None:
    d = Diagram(nodes=[_node("c", C4Type.CONTAINER), _node("db", C4Type.DATABASE)])
    assert ground_floating_nodes(d) == 0
    assert d.node_by_id("c4norm-conectividad") is None


def test_persons_and_systems_are_not_grounded() -> None:
    d = Diagram(
        nodes=[
            _node("site", C4Type.DEPLOYMENT_NODE),
            _node("p", C4Type.PERSON),
            _node("sys", C4Type.SOFTWARE_SYSTEM),
            _node("c", C4Type.CONTAINER),
        ]
    )
    grounded = ground_floating_nodes(d)
    assert grounded == 1  # solo el container
    assert d.node_by_id("p").parent is None
    assert d.node_by_id("sys").parent is None
    assert d.node_by_id("c").parent == "c4norm-conectividad"


def test_already_inside_boundary_not_regrounded() -> None:
    d = Diagram(
        nodes=[
            _node("site", C4Type.DEPLOYMENT_NODE),
            _node("c", C4Type.CONTAINER, parent="site"),
        ]
    )
    assert ground_floating_nodes(d) == 0  # 'c' ya tiene parent
    assert d.node_by_id("c4norm-conectividad") is None


def test_idempotent() -> None:
    d = Diagram(
        nodes=[
            _node("site", C4Type.DEPLOYMENT_NODE),
            _node("c", C4Type.CONTAINER),
        ]
    )
    assert ground_floating_nodes(d) == 1
    assert ground_floating_nodes(d) == 0  # segunda vez no re-ancla
    zones = [n for n in d.nodes if n.id == "c4norm-conectividad"]
    assert len(zones) == 1
