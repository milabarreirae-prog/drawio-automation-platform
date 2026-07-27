"""
Tests del spike de normalización C4 (c4norm).

Validan el lazo completo parse → clasificar → emitir sobre fixtures reales
(crudos de IA), y que la salida sea XML C4 bien formado y conforme.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from c4norm.classify import HeuristicClassifier
from c4norm.model import C4Type
from c4norm.normalize import normalize
from c4norm.parse import fix_mojibake, parse_drawio

FIXTURES = Path(__file__).parent / "fixtures"
IA2 = (FIXTURES / "crudo_ia_2_simple.drawio.xml").read_text(encoding="utf-8")
IA1 = (FIXTURES / "crudo_ia_1_deployment.drawio.xml").read_text(encoding="utf-8")


def _types(xml: str) -> dict[str, str]:
    """Mapa id → c4Type desde un XML C4 emitido."""
    root = etree.fromstring(xml.encode("utf-8"))
    return {o.get("id"): o.get("c4Type") for o in root.iter("object") if o.get("c4Type") != "Relationship"}


class TestParse:
    def test_accepts_bare_mxgraphmodel(self) -> None:
        diagrams = parse_drawio(IA1)
        assert len(diagrams) == 1
        assert len(diagrams[0].nodes) > 10

    def test_accepts_mxfile_wrapper(self) -> None:
        diagrams = parse_drawio(IA2)
        assert len(diagrams) == 1
        # 6 vértices, 5 aristas
        assert len(diagrams[0].nodes) == 6
        assert len(diagrams[0].edges) == 5

    def test_fix_mojibake_roundtrip(self) -> None:
        assert fix_mojibake("PeticiÃ³n Transaccional") == "Petición Transaccional"
        assert fix_mojibake("RegiÃ³n rÃ©plica") == "Región réplica"

    def test_clean_text_is_untouched(self) -> None:
        assert fix_mojibake("Petición Transaccional") == "Petición Transaccional"


class TestClassifyIA2:
    def setup_method(self) -> None:
        self.diagram = parse_drawio(IA2)[0]
        HeuristicClassifier().classify(self.diagram, c4_level=2)

    def test_actor_is_person(self) -> None:
        assert self.diagram.node_by_id("user").c4_type is C4Type.PERSON

    def test_cylinder_is_database(self) -> None:
        assert self.diagram.node_by_id("db").c4_type is C4Type.DATABASE

    def test_generic_boxes_are_containers_at_level_2(self) -> None:
        for nid in ("frontend", "api", "ms1", "kafka"):
            assert self.diagram.node_by_id(nid).c4_type is C4Type.CONTAINER

    def test_level_1_promotes_boxes_to_systems(self) -> None:
        d = parse_drawio(IA2)[0]
        HeuristicClassifier().classify(d, c4_level=1)
        assert d.node_by_id("frontend").c4_type is C4Type.SOFTWARE_SYSTEM


class TestClassifyIA1:
    def setup_method(self) -> None:
        self.diagram = parse_drawio(IA1)[0]
        HeuristicClassifier().classify(self.diagram, c4_level=2)

    def test_swimlanes_are_deployment_nodes(self) -> None:
        for nid in ("10", "11", "12"):
            assert self.diagram.node_by_id(nid).c4_type is C4Type.DEPLOYMENT_NODE

    def test_cylinder3_is_database(self) -> None:
        # 'amadeus1' usa shape=cylinder3 (variante inválida) → debe ser Database
        assert self.diagram.node_by_id("70").c4_type is C4Type.DATABASE

    def test_metadata_goes_to_description_not_name(self) -> None:
        node = self.diagram.node_by_id("200")
        assert node.c4_name == "DNS / GSLB"
        # 'Redirección … no validada' es la descripción real del autor.
        assert "no validada" in node.c4_description

    def test_governance_metadata_extracted_to_structured_fields(self) -> None:
        # Confianza / Estado CMDB del autor van a su capa, NO a la descripción.
        node = self.diagram.node_by_id("200")
        assert node.confidence == "Baja"
        assert node.cmdb_status == "Pendiente"
        assert "Confianza" not in node.c4_description
        assert "CMDB" not in node.c4_description


class TestEmit:
    def test_governance_badge_rendered_in_node_label(self) -> None:
        xml, _ = normalize(IA1, c4_level=2)
        root = etree.fromstring(xml.encode("utf-8"))
        labels = {o.get("id"): o.get("label", "") for o in root.iter("object")}
        # El badge muestra la gobernanza declarada por el autor, no inventada.
        assert "Confianza: Baja" in labels["200"]
        assert "CMDB: Pendiente" in labels["200"]

    def test_no_badge_when_author_declared_none(self) -> None:
        # IA2 no trae metadata de gobernanza → ningún nodo debe mostrar badge.
        xml, _ = normalize(IA2, c4_level=2)
        assert "Confianza:" not in xml
        assert "CMDB:" not in xml

    def test_ia2_emits_well_formed_c4(self) -> None:
        xml, report = normalize(IA2, c4_level=2)
        root = etree.fromstring(xml.encode("utf-8"))  # no debe lanzar
        assert root.tag == "mxfile"
        types = _types(xml)
        assert types["user"] == "Person"
        assert types["db"] == "Database"
        assert types["ms1"] == "Container"
        assert report.node_count == 6
        assert report.edge_count == 5

    def test_emitted_uses_canonical_c4_palette(self) -> None:
        xml, _ = normalize(IA2, c4_level=2)
        # Color canónico de Container y de Person presentes.
        assert "#438DD5" in xml  # Container
        assert "#08427b" in xml  # Person

    def test_no_overlap_in_layout(self) -> None:
        xml, _ = normalize(IA2, c4_level=2)
        root = etree.fromstring(xml.encode("utf-8"))
        boxes = []
        for obj in root.iter("object"):
            if obj.get("c4Type") == "Relationship":
                continue
            geo = obj.find(".//mxGeometry")
            if geo is None or geo.get("x") is None:
                continue
            x, y = float(geo.get("x")), float(geo.get("y"))
            w, h = float(geo.get("width")), float(geo.get("height"))
            boxes.append((x, y, w, h))
        # Verificar que no hay dos cajas con solape de área > 0.
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                ax, ay, aw, ah = boxes[i]
                bx, by, bw, bh = boxes[j]
                overlap_x = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
                overlap_y = max(0.0, min(ay + ah, by + bh) - max(ay, by))
                assert overlap_x * overlap_y == 0.0, f"solape entre cajas {i} y {j}"

    def test_ia1_runs_end_to_end(self) -> None:
        xml, report = normalize(IA1, c4_level=2)
        etree.fromstring(xml.encode("utf-8"))  # bien formado
        assert report.node_count > 10
        assert "DeploymentNode" in report.type_histogram

    def test_sheet_has_frame_and_title_block(self) -> None:
        xml, report = normalize(IA2, c4_level=2)
        assert "c4norm-frame" in xml
        assert "c4norm-tb-title" in xml
        assert "PROYECTO" in xml and "Escala" in xml
        assert report.scale.startswith("1:")

    def test_vertical_tree_increasing_y_along_flow(self) -> None:
        # En árbol vertical (TB), el target queda más abajo que el source.
        xml, _ = normalize(IA2, c4_level=2)
        root = etree.fromstring(xml.encode("utf-8"))
        ys = {}
        for obj in root.iter("object"):
            if obj.get("c4Type") == "Relationship":
                continue
            geo = obj.find(".//mxGeometry")
            if geo is not None and geo.get("y") is not None:
                ys[obj.get("id")] = float(geo.get("y"))
        assert ys["frontend"] > ys["user"]  # frontend debajo de user
        assert ys["ms1"] > ys["api"]


class TestGrounding:
    def test_ia1_grounds_floating_infra(self) -> None:
        xml, report = normalize(IA1, c4_level=2)
        # DNS/WAN/NAT (red) estaban sueltos → deben quedar anclados.
        assert report.grounded_nodes >= 3
        assert "c4norm-conectividad" in xml
        root = etree.fromstring(xml.encode("utf-8"))
        parents = {
            o.get("id"): o.find(".//mxCell").get("parent")
            for o in root.iter("object")
            if o.get("c4Type") != "Relationship"
        }
        for nid in ("200", "201", "212"):
            assert parents[nid] == "c4norm-conectividad"

    def test_ia2_grounds_nothing(self) -> None:
        # Un flujo simple sin sitios no debe meterse en una caja "Red".
        _, report = normalize(IA2, c4_level=2)
        assert report.grounded_nodes == 0


class TestLayoutEngine:
    def test_layered_fallback_emits_valid_xml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Forzar el fallback en Python puro (sin ELK) debe seguir funcionando.
        monkeypatch.setenv("C4NORM_LAYOUT", "layered")
        xml, report = normalize(IA2, c4_level=2)
        etree.fromstring(xml.encode("utf-8"))
        assert report.engine == "LayeredLayout"

    def test_elk_used_when_available_and_routes_branches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from c4norm.layout.elk import ElkLayout

        if not ElkLayout().available():
            pytest.skip("ELK (Node/elkjs) no disponible en este entorno")
        monkeypatch.setenv("C4NORM_LAYOUT", "elk")
        xml, report = normalize(IA2, c4_level=2)
        assert report.engine == "ElkLayout"
        # La rama ms1→kafka debe rutearse con waypoints (esquiva la BD).
        assert "<Array as=\"points\">" in xml


@pytest.mark.parametrize("level", [1, 2, 3])
def test_all_levels_emit_valid_xml(level: int) -> None:
    xml, _ = normalize(IA2, c4_level=level)
    etree.fromstring(xml.encode("utf-8"))
