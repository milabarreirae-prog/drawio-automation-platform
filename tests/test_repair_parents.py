"""
Tests de la reparación de padres colgantes (`repair_dangling_parents`).

Un nodo cuyo ``parent`` referencia un id inexistente desaparecería del diagrama:
el layout no lo posiciona y draw.io descarta las celdas huérfanas de padre. El
motor jamás debe perder un elemento (el dual de «nunca inventar»).
"""

from __future__ import annotations

from c4norm.model import C4Type, Diagram, Node
from c4norm.normalize import normalize
from c4norm.parse import parse_drawio, repair_dangling_parents


def test_promotes_node_with_missing_parent_to_top_level() -> None:
    d = Diagram(
        nodes=[
            Node(id="a", c4_type=C4Type.CONTAINER, parent="fantasma"),
            Node(id="b", c4_type=C4Type.CONTAINER),
        ]
    )
    assert repair_dangling_parents(d) == 1
    assert d.node_by_id("a").parent is None  # promovido, no perdido


def test_valid_parent_is_preserved() -> None:
    d = Diagram(
        nodes=[
            Node(id="site", c4_type=C4Type.DEPLOYMENT_NODE),
            Node(id="c", c4_type=C4Type.CONTAINER, parent="site"),
        ]
    )
    assert repair_dangling_parents(d) == 0
    assert d.node_by_id("c").parent == "site"  # contención legítima intacta


def test_idempotent() -> None:
    d = Diagram(nodes=[Node(id="a", c4_type=C4Type.CONTAINER, parent="fantasma")])
    assert repair_dangling_parents(d) == 1
    assert repair_dangling_parents(d) == 0


# XML con un nodo cuyo parent="phantom" no corresponde a ninguna celda real:
# antes de la reparación desaparecería del diagrama emitido.
_XML_DANGLING = """<mxGraphModel>
  <root>
    <mxCell id="0" />
    <mxCell id="1" parent="0" />
    <mxCell id="keep" value="Servicio de Pagos" style="rounded=1;" vertex="1" parent="1">
      <mxGeometry x="40" y="40" width="120" height="60" as="geometry" />
    </mxCell>
    <mxCell id="ghost-child" value="Base de Datos" style="shape=cylinder3;" vertex="1" parent="phantom">
      <mxGeometry x="20" y="20" width="80" height="80" as="geometry" />
    </mxCell>
  </root>
</mxGraphModel>"""


def test_parse_drawio_repairs_dangling_parent() -> None:
    diagram = parse_drawio(_XML_DANGLING)[0]
    child = diagram.node_by_id("ghost-child")
    assert child is not None
    assert child.parent is None  # 'phantom' no existe → promovido a top-level


def test_node_survives_into_emitted_xml() -> None:
    xml_c4, report = normalize(_XML_DANGLING, c4_level=2)
    # El nodo antes condenado a desaparecer sigue presente en la salida...
    assert 'id="ghost-child"' in xml_c4
    # ...y emitido con un padre válido (nunca parent="phantom", que draw.io descarta).
    assert 'parent="phantom"' not in xml_c4
    assert report.node_count == 2
