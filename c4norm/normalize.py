"""
Orquestador del pipeline de normalización C4.

    parse → (reparar) → clasificar C4 → [enriquecer IA] → emitir C4 (+ cajetín)

Punto de entrada: ``normalize(xml_content, c4_level, classifier, title_block)``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from c4norm.classify import enforce_container_types, get_classifier
from c4norm.emit import emit_c4
from c4norm.enrich import Enricher
from c4norm.ground import ground_floating_nodes
from c4norm.legend import build_standard_legend
from c4norm.model import C4Type, Diagram
from c4norm.parse import label_to_text, parse_drawio
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
    annotation_count: int = 0
    edge_count: int = 0
    inferred_edges: int = 0
    grounded_nodes: int = 0
    merged_nodes: int = 0
    enriched: bool = False
    type_histogram: dict[str, int] = field(default_factory=dict)
    low_confidence: list[str] = field(default_factory=list)
    changelog: list[str] = field(default_factory=list)
    scale: str = "1:1"
    overflow: bool = False
    sheet: str = "A3"
    orientation: str = "landscape"
    engine: str = ""
    sheets: int = 1
    cross_sheet_edges: int = 0
    input_page_count: int = 1
    warnings: list[str] = field(default_factory=list)

    def to_api_dict(self) -> dict:
        """Serializa a dict para NormalizeReportModel (única fuente de verdad del mapping)."""
        import dataclasses
        return dataclasses.asdict(self)


def _install_standard_legend(diagram: Diagram) -> None:
    """Descarta la leyenda original (colores ya inválidos) y ancla una clave C4 estándar."""
    kept = [a for a in diagram.annotations if a.kind != "legend"]
    if kept:
        ax = min(a.x for a in kept)
        ay = max(a.y + a.height for a in kept) + 40
    else:
        ax, ay = 0.0, 0.0
    diagram.annotations = kept + build_standard_legend(diagram, ax, ay)


def normalize(
    xml_content: str,
    c4_level: int = 2,
    classifier: str = "heuristic",
    title_block: TitleBlock | None = None,
    *,
    context: str = "",
    enrich: bool = False,
    enricher: Enricher | None = None,
) -> tuple[str, NormalizeReport]:
    """
    Normaliza un XML Draw.io crudo a XML C4 con hoja de ingeniería.
    Procesa solo la primera página.

    Args:
        context: documento de dominio (texto) que el LLM usa para enriquecer.
        enrich: si True y hay LLM, corre la pasada de enriquecimiento (potencia
            descripciones/relaciones, estandariza nombres, fusiona duplicados,
            integra título→cajetín y leyenda→clave C4 estándar).
        enricher: inyectable para tests (evita red).

    Returns:
        (xml_c4, report)
    """
    diagrams = parse_drawio(xml_content)
    if not diagrams:
        raise ValueError("No se encontró ningún diagrama en el XML")

    warnings: list[str] = []
    if len(diagrams) > 1:
        warnings.append(
            f"El XML tiene {len(diagrams)} páginas; solo se normaliza la primera "
            f"('{diagrams[0].name}'). Las demás se ignoran."
        )

    diagram = diagrams[0]
    clf = get_classifier(classifier)
    clf.classify(diagram, c4_level)

    # Invariante: los nodos con hijos deben ser DeploymentNode (único boundary del
    # spec). Corrige degradaciones del clasificador que romperían el anidamiento.
    retyped_containers = enforce_container_types(diagram)
    if retyped_containers:
        warnings.append(
            f"{retyped_containers} nodo(s) con hijos se reclasificaron a DeploymentNode "
            f"para preservar el anidamiento (un contenedor no puede ser un tipo hoja)."
        )

    # Pasada de enriquecimiento con IA (opcional): potencia el diagrama con el
    # contexto de dominio, estandariza, fusiona duplicados e integra título/leyenda.
    changelog: list[str] = []
    merged_nodes = 0
    enriched = False
    enrich_title = ""
    if enrich:
        eng = enricher
        if eng is None and os.environ.get("C4NORM_LLM_API_KEY"):
            eng = Enricher()
        if eng is None:
            warnings.append("Enriquecimiento omitido: falta C4NORM_LLM_API_KEY.")
        else:
            try:
                res = eng.enrich(diagram, c4_level, context)
                enriched = True
                changelog = res.changelog
                merged_nodes = res.merged
                enrich_title = res.title
                # Título → cajetín: la nota-título deja de flotar en la banda. Se quita por
                # id (el LLM lo señala) y, como respaldo, por coincidencia de texto.
                norm = enrich_title.strip().lower()
                diagram.annotations = [
                    a for a in diagram.annotations
                    if a.id != res.title_id
                    and not (norm and a.kind in ("text", "note") and label_to_text(a.value).strip().lower() == norm)
                ]
                # Leyenda → clave C4 estándar (la original quedó inválida al recolorear por tipo).
                _install_standard_legend(diagram)
            except ValueError as exc:
                warnings.append(f"Enriquecimiento omitido: {exc}")

    grounded = ground_floating_nodes(diagram)

    histogram: dict[str, int] = {}
    low_conf: list[str] = []
    for node in diagram.nodes:
        t = (node.c4_type or C4Type.CONTAINER).value
        histogram[t] = histogram.get(t, 0) + 1
        if not node.explicit_c4_type and not node.raw_label.strip():
            low_conf.append(node.id)

    tb = title_block or TitleBlock(title=diagram.name)
    if enrich_title and (title_block is None or not getattr(title_block, "title", "")):
        tb.title = enrich_title
    result = emit_c4(diagram, c4_level, title_block=tb)

    report = NormalizeReport(
        diagram_name=diagram.name,
        c4_level=c4_level,
        node_count=len(diagram.nodes),
        annotation_count=len(diagram.annotations),
        edge_count=len(diagram.edges),
        inferred_edges=sum(1 for e in diagram.edges if e.inferred),
        grounded_nodes=grounded,
        merged_nodes=merged_nodes,
        enriched=enriched,
        type_histogram=histogram,
        low_confidence=low_conf,
        changelog=changelog,
        scale=result.scale,
        overflow=result.overflow,
        sheet=result.sheet,
        orientation=result.orientation,
        engine=result.engine,
        sheets=result.sheets,
        cross_sheet_edges=result.cross_sheet_edges,
        input_page_count=len(diagrams),
        warnings=warnings,
    )
    return result.xml, report
