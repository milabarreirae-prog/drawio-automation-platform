"""
Parseo y normalización de entrada: XML Draw.io → modelo lógico.

Acepta tanto ``<mxfile>`` como ``<mxGraphModel>`` pelado, sanea el encoding
(mojibake del round-trip de Confluence), extrae nodos/aristas (incluyendo
``<object>`` con metadata C4) y reconstruye aristas huérfanas por proximidad
geométrica. Ver docs/C4_NORMALIZER_DESIGN.md §4 (etapas 1-2).
"""

from __future__ import annotations

import html
import re

from lxml import etree

from c4norm.model import Annotation, Diagram, Edge, Node

_TAG = re.compile(r"<[^>]+>")
_BR = re.compile(r"<br\s*/?>|</div>|</p>", re.IGNORECASE)
_CONTAINER_HINTS = ("swimlane", "group", "mxgraph.c4.dynamic", "umllifeline")
#: Nombres (primera línea) que marcan un swimlane como leyenda/notas → anotación.
_ANNOTATION_NAMES = {"leyenda", "legend", "notas", "notes", "convenciones"}


# =============================================================================
# Saneo de texto (mojibake del round-trip Confluence/Atlassian)
# =============================================================================


def fix_mojibake(text: str) -> str:
    """
    Repara doble-codificación UTF-8↔CP1252 (``PeticiÃ³n`` → ``Petición``).

    Heurística ligera (sin dependencia de ftfy): si aparecen secuencias típicas
    de mojibake, se reinterpreta el texto como CP1252→UTF-8. Es idempotente sobre
    texto ya correcto en la práctica para estos diagramas.
    """
    if "Ã" not in text and "â" not in text:
        return text
    try:
        repaired = text.encode("cp1252", errors="strict").decode("utf-8", errors="strict")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    # Solo aceptar la reparación si reduce los marcadores de mojibake.
    if (repaired.count("Ã") + repaired.count("â")) < (text.count("Ã") + text.count("â")):
        return repaired
    return text


def label_to_text(label: str) -> str:
    """Convierte una etiqueta HTML de draw.io en texto plano con saltos de línea."""
    if not label:
        return ""
    text = _BR.sub("\n", label)
    text = _TAG.sub("", text)
    text = html.unescape(text)
    text = fix_mojibake(text)
    lines = [ln.strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


# =============================================================================
# Parseo de estilo
# =============================================================================


def parse_style(style: str) -> dict[str, str]:
    """Convierte ``a=1;b=2;shape=x`` en dict. Las claves sin ``=`` quedan con ''."""
    out: dict[str, str] = {}
    for part in (style or "").split(";"):
        part = part.strip()
        if not part:
            continue
        key, _, value = part.partition("=")
        out[key.strip()] = value.strip()
    return out


# =============================================================================
# Extracción de modelo lógico
# =============================================================================


def _geometry(cell: etree._Element) -> tuple[float, float, float, float]:
    geo = cell.find("mxGeometry")
    if geo is None:
        return 0.0, 0.0, 120.0, 60.0
    fget = lambda k, d: float(geo.get(k, d))  # noqa: E731
    return fget("x", "0"), fget("y", "0"), fget("width", "120"), fget("height", "60")


def _edge_points(cell: etree._Element) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    geo = cell.find("mxGeometry")
    src = tgt = None
    if geo is not None:
        for pt in geo.findall("mxPoint"):
            kind = pt.get("as")
            xy = (float(pt.get("x", "0")), float(pt.get("y", "0")))
            if kind == "sourcePoint":
                src = xy
            elif kind == "targetPoint":
                tgt = xy
    return src, tgt


def _strip_namespaces(root: etree._Element) -> None:
    """Elimina prefijos de namespace Clark ({uri}tag → tag) de todo el árbol.

    Algunos exporters incluyen xmlns="http://..." en el mxfile; sin esto,
    root.iter("diagram") no encontraría nada porque los tags tendrían la forma
    {http://diagrams.net/schema/mxfile}diagram.

    Sólo procesa elementos (no comments ni PI cuyo .tag es una función, no str).
    """
    for elem in root.iter():
        if not isinstance(elem.tag, str):
            continue
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]


def _iter_graph_models(root: etree._Element) -> list[tuple[str, etree._Element]]:
    """Devuelve [(nombre_pagina, mxGraphModel)] tanto para mxfile como pelado."""
    if root.tag == "mxGraphModel":
        return [("Diagram", root)]
    models: list[tuple[str, etree._Element]] = []
    for diag in root.iter("diagram"):
        gm = diag.find("mxGraphModel")
        if gm is not None:
            models.append((diag.get("name", "Diagram"), gm))
    if not models:
        gm = root.find(".//mxGraphModel")
        if gm is not None:
            models.append(("Diagram", gm))
    return models


def _build_diagram(name: str, gm: etree._Element) -> Diagram:
    root_el = gm.find("root")
    if root_el is None:
        return Diagram(name=name)

    diagram = Diagram(name=name)
    seen_cells: set[etree._Element] = set()
    # Posición absoluta acumulada por id (para reubicar anotaciones anidadas) y
    # conjunto de ids que son anotación (para arrastrar el subárbol de la leyenda).
    abs_pos: dict[str, tuple[float, float]] = {}
    anno_ids: set[str] = set()

    # 1) Nodos/aristas envueltos en <object> (portan metadata c4*).
    for obj in root_el.findall("object"):
        cell = obj.find("mxCell")
        if cell is None:
            continue
        seen_cells.add(cell)
        node_id = obj.get("id") or cell.get("id") or ""
        label = obj.get("label", "")
        c4_type = obj.get("c4Type")
        _ingest(diagram, node_id, cell, label, c4_type, abs_pos, anno_ids)

    # 2) mxCell sueltos (no dentro de un object).
    for cell in root_el.iter("mxCell"):
        if cell in seen_cells:
            continue
        node_id = cell.get("id", "")
        if node_id in ("0", "1") or not node_id:
            continue
        _ingest(diagram, node_id, cell, cell.get("value", ""), None, abs_pos, anno_ids)

    # Las aristas que tocan una anotación no son relaciones C4: se descartan.
    if anno_ids:
        diagram.edges = [
            e for e in diagram.edges if e.source not in anno_ids and e.target not in anno_ids
        ]

    return diagram


def _annotation_kind(style: str, parsed: dict[str, str], label: str, is_container: bool) -> str | None:
    """Clasifica la celda como anotación y devuelve su clase, o ``None`` si es nodo C4.

    Estas celdas NO son nodos C4: se preservan en una capa aparte (``Annotation``)
    en vez de clasificarse —erróneamente— como componentes. Se detectan por:
      * ``shape=note``            → ``"note"``  (post-it),
      * primer token ``text``     → ``"text"``  (título, fases, rótulos sueltos),
      * swimlane cuyo nombre sea  → ``"legend"`` (leyenda/convenciones; su subárbol también).
    """
    if parsed.get("shape") == "note":
        return "note"
    if style.split(";", 1)[0].strip() == "text":
        return "text"
    if is_container:
        first = label_to_text(label).split("\n", 1)[0].strip().lower()
        if first in _ANNOTATION_NAMES:
            return "legend"
    return None


def _ingest(
    diagram: Diagram,
    node_id: str,
    cell: etree._Element,
    label: str,
    c4_type: str | None,
    abs_pos: dict[str, tuple[float, float]],
    anno_ids: set[str],
) -> None:
    style = cell.get("style", "")
    parsed = parse_style(style)
    parent = cell.get("parent")

    if cell.get("edge") == "1":
        src_pt, tgt_pt = _edge_points(cell)
        diagram.edges.append(
            Edge(
                id=node_id,
                source=cell.get("source"),
                target=cell.get("target"),
                raw_label=label_to_text(label),
                source_point=src_pt,
                target_point=tgt_pt,
            )
        )
        return

    if cell.get("vertex") != "1":
        return

    x, y, w, h = _geometry(cell)
    shape = parsed.get("shape", "")
    is_container = (
        any(h in style.lower() for h in _CONTAINER_HINTS)
        or parsed.get("container") == "1"
        or "group" in style.lower()
    )

    # Posición absoluta (acumula el offset de los padres ya vistos en orden).
    px, py = abs_pos.get(parent or "", (0.0, 0.0))
    abs_x, abs_y = px + x, py + y
    abs_pos[node_id] = (abs_x, abs_y)

    # Capa de anotaciones: nota/texto/leyenda (o hijo de una) → se preserva, no
    # se clasifica como nodo C4. Se guarda con etiqueta y estilo originales.
    kind = "legend" if parent in anno_ids else _annotation_kind(style, parsed, label, is_container)
    if kind is not None:
        anno_ids.add(node_id)
        diagram.annotations.append(
            Annotation(id=node_id, value=label, style=style, kind=kind, x=abs_x, y=abs_y, width=w, height=h)
        )
        return

    diagram.nodes.append(
        Node(
            id=node_id,
            raw_label=label_to_text(label),
            raw_style=parsed,
            shape=shape,
            parent=parent if parent not in ("1", "0") else None,
            is_container_src=is_container,
            x=x,
            y=y,
            width=w,
            height=h,
            explicit_c4_type=c4_type,
        )
    )


# =============================================================================
# Reparación: aristas huérfanas → enganche por proximidad
# =============================================================================


def reconnect_orphan_edges(diagram: Diagram, threshold: float = 40.0) -> int:
    """
    Para aristas sin source/target pero con coordenadas, engancha al nodo cuyo
    bounding-box contiene/está más cerca del extremo. Devuelve cuántas reparó.
    """
    repaired = 0
    for edge in diagram.edges:
        if edge.source and edge.target:
            continue
        if not edge.source and edge.source_point:
            hit = _nearest_node(diagram, edge.source_point, threshold)
            if hit:
                edge.source, edge.inferred = hit.id, True
        if not edge.target and edge.target_point:
            hit = _nearest_node(diagram, edge.target_point, threshold)
            if hit:
                edge.target, edge.inferred = hit.id, True
        if edge.inferred and edge.source and edge.target:
            repaired += 1
    return repaired


def _nearest_node(diagram: Diagram, point: tuple[float, float], threshold: float) -> Node | None:
    px, py = point
    best: Node | None = None
    best_dist = float("inf")
    for node in diagram.nodes:
        if node.is_container_src:
            continue
        # Punto dentro del bounding-box → match inmediato.
        if node.x - threshold <= px <= node.x + node.width + threshold and (
            node.y - threshold <= py <= node.y + node.height + threshold
        ):
            dist = (px - node.cx) ** 2 + (py - node.cy) ** 2
            if dist < best_dist:
                best_dist, best = dist, node
    return best


def repair_dangling_parents(diagram: Diagram) -> int:
    """
    Repara nodos cuyo ``parent`` apunta a un id que no es otro nodo del diagrama
    (contenedor inexistente, borrado, o mal referenciado por la IA).

    Sin reparar, ese nodo **desaparece**: el layout no lo posiciona (no es top-level
    ni hijo de un nodo real) y draw.io descarta las celdas cuyo padre no existe. Se
    promueve a nivel superior (``parent=None``) para que participe del layout y se
    emita visible; el anclaje posterior (``ground_floating_nodes``) lo coloca en su
    zona si procede. No inventa contenedor alguno: sólo evita perder el nodo (el dual
    de «nunca inventar» es «nunca perder»). Devuelve cuántos reparó.
    """
    node_ids = {n.id for n in diagram.nodes}
    repaired = 0
    for node in diagram.nodes:
        if node.parent is not None and node.parent not in node_ids:
            node.parent = None
            repaired += 1
    return repaired


def parse_drawio(xml_content: str) -> list[Diagram]:
    """Parsea XML Draw.io (mxfile o mxGraphModel pelado) a modelos lógicos.

    ``recover=True`` tolera cosas benignas del mundo real (namespaces con prefijo,
    entidades sueltas de un round-trip de Confluence, etc.), pero libxml2 usa el
    MISMO modo de recuperación para truncamiento/corrupción real: un ``.drawio``
    cortado a la mitad (descarga interrumpida, disco lleno, merge mal resuelto)
    puede "recuperarse" en un árbol parcial que descarta justo los nodos que
    venían después del corte — indistinguible de un diagrama genuinamente vacío
    (Ax-C4N-001 / R1 "el vacío se afirma": ninguna falla del productor puede
    aterrizar en la misma vista que un vacío real). Por eso se revisa
    ``parser.error_log``: si libxml2 tuvo que recuperarse de un error real de
    sintaxis, se rechaza el documento en vez de emitir en silencio lo poco que
    sobrevivió al corte.
    """
    parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True, load_dtd=False)
    root = etree.fromstring(xml_content.encode("utf-8"), parser=parser)
    if root is None:
        raise ValueError("XML vacío o no parseable")
    if len(parser.error_log) > 0:
        first = parser.error_log[0]
        raise ValueError(
            f"XML Draw.io corrupto o truncado: {len(parser.error_log)} error(es) de "
            f"sintaxis recuperados por el parser (p.ej. línea {first.line}: {first.message}). "
            "No se normaliza un documento que el parser tuvo que reconstruir a medias: "
            "podría estar descartando contenido real de forma indistinguible de un "
            "diagrama vacío."
        )
    _strip_namespaces(root)

    diagrams: list[Diagram] = []
    for name, gm in _iter_graph_models(root):
        diagram = _build_diagram(name, gm)
        reconnect_orphan_edges(diagram)
        repair_dangling_parents(diagram)
        diagrams.append(diagram)
    return diagrams
