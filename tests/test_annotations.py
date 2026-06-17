"""
Tests de la capa de anotaciones: notas, textos sueltos y leyendas se preservan
COMO documentación (no se clasifican como nodos C4) y se reubican en una banda
bajo el contenido del diagrama, conservando estilo y etiqueta originales.
"""

from __future__ import annotations

from lxml import etree

from c4norm.normalize import normalize
from c4norm.parse import parse_drawio

# Fixture: 2 nodos reales + nota + texto + leyenda(con hijo) + arista real + arista a nota.
_XML = """<mxGraphModel><root>
  <mxCell id="0"/><mxCell id="1" parent="0"/>
  <mxCell id="svc" value="Servicio API" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">
    <mxGeometry x="40" y="40" width="160" height="60" as="geometry"/>
  </mxCell>
  <mxCell id="db" value="Base" style="shape=datastore;whiteSpace=wrap;html=1;" vertex="1" parent="1">
    <mxGeometry x="40" y="160" width="120" height="80" as="geometry"/>
  </mxCell>
  <mxCell id="note1" value="Nota: por validar" style="shape=note;whiteSpace=wrap;html=1;fillColor=#fff2cc;" vertex="1" parent="1">
    <mxGeometry x="300" y="40" width="160" height="80" as="geometry"/>
  </mxCell>
  <mxCell id="title" value="Mi Diagrama" style="text;html=1;strokeColor=none;fillColor=none;" vertex="1" parent="1">
    <mxGeometry x="40" y="0" width="200" height="30" as="geometry"/>
  </mxCell>
  <mxCell id="leg" value="Leyenda" style="swimlane;horizontal=0;fontStyle=1;" vertex="1" parent="1">
    <mxGeometry x="300" y="200" width="200" height="120" as="geometry"/>
  </mxCell>
  <mxCell id="legitem" value="Ejemplo" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="leg">
    <mxGeometry x="20" y="40" width="120" height="40" as="geometry"/>
  </mxCell>
  <mxCell id="e_real" value="usa" edge="1" source="svc" target="db" parent="1">
    <mxGeometry relative="1" as="geometry"/>
  </mxCell>
  <mxCell id="e_anno" value="apunta" edge="1" source="svc" target="note1" parent="1">
    <mxGeometry relative="1" as="geometry"/>
  </mxCell>
</root></mxGraphModel>"""


# =============================================================================
# Parseo: separación nodos C4 / anotaciones
# =============================================================================

def _diagram():
    return parse_drawio(_XML)[0]


def test_notes_and_text_are_annotations_not_nodes() -> None:
    d = _diagram()
    node_ids = {n.id for n in d.nodes}
    anno_ids = {a.id for a in d.annotations}
    assert node_ids == {"svc", "db"}          # sólo arquitectura real
    assert {"note1", "title"} <= anno_ids      # nota y texto → anotación


def test_legend_swimlane_and_children_are_annotations() -> None:
    d = _diagram()
    anno_ids = {a.id for a in d.annotations}
    assert "leg" in anno_ids        # swimlane "Leyenda"
    assert "legitem" in anno_ids    # su hijo, arrastrado al subárbol
    assert "legitem" not in {n.id for n in d.nodes}


def test_annotation_child_uses_absolute_coords() -> None:
    d = _diagram()
    item = next(a for a in d.annotations if a.id == "legitem")
    # leg en (300,200) + hijo (20,40) → absoluto (320,240)
    assert (item.x, item.y) == (320, 240)


def test_annotation_preserves_value_and_style() -> None:
    d = _diagram()
    note = next(a for a in d.annotations if a.id == "note1")
    assert note.value == "Nota: por validar"
    assert "shape=note" in note.style
    assert "fillColor=#fff2cc" in note.style


def test_edges_touching_annotations_are_dropped() -> None:
    d = _diagram()
    edge_ids = {e.id for e in d.edges}
    assert "e_real" in edge_ids     # svc → db, relación real
    assert "e_anno" not in edge_ids  # svc → note1, descartada


# =============================================================================
# Normalización completa: emisión + reporte
# =============================================================================

def test_report_counts_annotations_separately() -> None:
    _xml, rep = normalize(_XML, c4_level=3, classifier="heuristic")
    assert rep.node_count == 2
    assert rep.annotation_count == 4   # note1, title, leg, legitem
    # las anotaciones NO contaminan el histograma de tipos C4
    assert sum(rep.type_histogram.values()) == rep.node_count


def test_emitted_xml_has_annotation_cells() -> None:
    xml_c4, _rep = normalize(_XML, c4_level=3, classifier="heuristic")
    root = etree.fromstring(xml_c4.encode())
    anno_ids = {c.get("id") for c in root.iter("mxCell") if (c.get("id") or "").startswith("anno-")}
    assert anno_ids == {"anno-note1", "anno-title", "anno-leg", "anno-legitem"}


def test_annotation_cells_keep_original_style_and_text() -> None:
    xml_c4, _rep = normalize(_XML, c4_level=3, classifier="heuristic")
    root = etree.fromstring(xml_c4.encode())
    note = next(c for c in root.iter("mxCell") if c.get("id") == "anno-note1")
    assert "shape=note" in note.get("style", "")
    assert note.get("value") == "Nota: por validar"
    # no es un objeto C4: sin metadata c4Type
    assert note.getparent().tag == "root"


def test_annotations_render_below_c4_content() -> None:
    """La banda de anotaciones queda por debajo del contenido C4 (mayor y)."""
    xml_c4, _rep = normalize(_XML, c4_level=3, classifier="heuristic")
    root = etree.fromstring(xml_c4.encode())

    def y_of(cell):
        geo = cell.find("mxGeometry")
        return float(geo.get("y")) if geo is not None else 0.0

    # y de los nodos C4 (objetos) vs y de las anotaciones
    node_ys = [y_of(o.find("mxCell")) for o in root.iter("object")
               if o.get("c4Type") and o.get("c4Type") != "Relationship"]
    anno_ys = [y_of(c) for c in root.iter("mxCell") if (c.get("id") or "").startswith("anno-")]
    assert node_ys and anno_ys
    # la anotación más alta arranca por debajo del nodo C4 más bajo
    assert min(anno_ys) >= max(node_ys)


def test_diagram_without_annotations_still_works() -> None:
    xml_no_anno = """<mxGraphModel><root>
      <mxCell id="0"/><mxCell id="1" parent="0"/>
      <mxCell id="a" value="Solo nodo" style="rounded=1;" vertex="1" parent="1">
        <mxGeometry x="0" y="0" width="120" height="60" as="geometry"/>
      </mxCell>
    </root></mxGraphModel>"""
    xml_c4, rep = normalize(xml_no_anno, c4_level=2, classifier="heuristic")
    assert rep.annotation_count == 0
    assert "anno-" not in xml_c4
