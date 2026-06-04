"""
Orquestador del pipeline de normalización C4.

    parse → (reparar) → clasificar C4 → emitir C4 (árbol vertical + cajetín)

Punto de entrada: ``normalize(xml_content, c4_level, classifier, title_block)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from c4norm.classify import get_classifier
from c4norm.emit import emit_c4
from c4norm.ground import ground_floating_nodes
from c4norm.model import C4Type
from c4norm.parse import parse_drawio
from c4norm.sheet import TitleBlock


@dataclass
class NormalizeReport:
    """Resumen de qué hizo el motor (para inspección/QA).

    Usar ``to_api_dict()`` para serializar a la API: centraliza el mapping
    y garantiza que campos nuevos lleguen a ``NormalizeReportModel`` sin editar dos sitios.
    """

    diagram_name: str = ""
    c4_level: int = 2
    node_count: int = 0
    edge_count: int = 0
    inferred_edges: int = 0
    grounded_nodes: int = 0
    type_histogram: dict[str, int] = field(default_factory=dict)
    low_confidence: list[str] = field(default_factory=list)
    scale: str = "1:1"
    overflow: bool = False
    sheet: str = "A3"
    orientation: str = "landscape"
    engine: str = ""
    sheets: int = 1
    cross_sheet_edges: int = 0

    def to_api_dict(self) -> dict:
        """Serializa a dict para NormalizeReportModel (única fuente de verdad del mapping)."""
        import dataclasses
        return dataclasses.asdict(self)


def normalize(
    xml_content: str,
    c4_level: int = 2,
    classifier: str = "heuristic",
    title_block: TitleBlock | None = None,
) -> tuple[str, NormalizeReport]:
    """
    Normaliza un XML Draw.io crudo a XML C4 con hoja de ingeniería.
    Procesa solo la primera página.

    Returns:
        (xml_c4, report)
    """
    diagrams = parse_drawio(xml_content)
    if not diagrams:
        raise ValueError("No se encontró ningún diagrama en el XML")

    diagram = diagrams[0]
    clf = get_classifier(classifier)
    clf.classify(diagram, c4_level)

    grounded = ground_floating_nodes(diagram)

    histogram: dict[str, int] = {}
    low_conf: list[str] = []
    for node in diagram.nodes:
        t = (node.c4_type or C4Type.CONTAINER).value
        histogram[t] = histogram.get(t, 0) + 1
        if not node.explicit_c4_type and not node.raw_label.strip():
            low_conf.append(node.id)

    tb = title_block or TitleBlock(title=diagram.name)
    result = emit_c4(diagram, c4_level, title_block=tb)

    report = NormalizeReport(
        diagram_name=diagram.name,
        c4_level=c4_level,
        node_count=len(diagram.nodes),
        edge_count=len(diagram.edges),
        inferred_edges=sum(1 for e in diagram.edges if e.inferred),
        grounded_nodes=grounded,
        type_histogram=histogram,
        low_confidence=low_conf,
        scale=result.scale,
        overflow=result.overflow,
        sheet=result.sheet,
        orientation=result.orientation,
        engine=result.engine,
        sheets=result.sheets,
        cross_sheet_edges=result.cross_sheet_edges,
    )
    return result.xml, report
