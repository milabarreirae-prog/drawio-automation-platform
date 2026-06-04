"""
Emisión C4 + hoja de ingeniería (ver docs/C4_NORMALIZER_DESIGN.md §4 y §8).

El layout lo provee un motor intercambiable (ELK real o fallback por capas). Si el
motor entrega rutas ortogonales (ELK), las líneas se dibujan con esos quiebres; si
no, se enrutan por lado. La página se ajusta al contenido (1:1, mínimo blanco) con
marco + cajetín ISO 7200.

**Multi-hoja:** si el diagrama no cabe ni al mínimo (`overflow`) y tiene ≥2
boundaries de nivel superior, se descompone en una hoja por boundary (vista de
deployment) más una hoja "Contexto" con personas/sistemas. Cada hoja se diagrama,
escala y rotula por separado ("Hoja N de M"). Las aristas que cruzan hojas se
cuentan (no se dibujan ni se inventan).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from xml.sax.saxutils import escape

from c4norm.layout import LayoutEngine, get_layout_engine, run_with_fallback
from c4norm.model import (
    C4_SPEC,
    RELATIONSHIP_STYLE,
    C4Type,
    Diagram,
    Node,
    external_style,
)
from c4norm.sheet import (
    DrawArea,
    TitleBlock,
    fit_page,
    render_frame_and_title_block,
    scale_string,
)

_BASE_FONT = 12
_MIN_SCALE = 0.45


@dataclass
class EmitResult:
    """Resultado de la emisión (1 o varias hojas)."""

    xml: str
    scale: str
    overflow: bool
    engine: str
    sheet: str
    orientation: str
    sheets: int = 1
    cross_sheet_edges: int = 0


# =============================================================================
# Encuadre y escala
# =============================================================================


def _content_bbox(diagram: Diagram) -> tuple[float, float]:
    top = [n for n in diagram.nodes if not n.parent]
    if not top:
        return 1.0, 1.0
    minx = min(n.x for n in top)
    miny = min(n.y for n in top)
    maxx = max(n.x + n.width for n in top)
    maxy = max(n.y + n.height for n in top)
    return max(1.0, maxx - minx), max(1.0, maxy - miny)


def _scale_only(diagram: Diagram, area: DrawArea) -> float:
    """Escala a la que el contenido cabe en `area` (sin mutar el diagrama)."""
    cw, ch = _content_bbox(diagram)
    return min(1.0, area.width / cw, area.height / ch)


def _fit(diagram: Diagram, area: DrawArea) -> tuple[float, bool]:
    top = [n for n in diagram.nodes if not n.parent]
    if not top:
        return 1.0, False
    cw, ch = _content_bbox(diagram)
    minx = min(n.x for n in top)
    miny = min(n.y for n in top)

    s = min(1.0, area.width / cw, area.height / ch)
    overflow = s < _MIN_SCALE
    s = max(s, _MIN_SCALE)

    offx = area.x0 + max(0.0, (area.width - cw * s) / 2)
    offy = area.y0 + max(0.0, (area.height - ch * s) / 2)

    def tx(px: float, py: float) -> tuple[float, float]:
        return offx + (px - minx) * s, offy + (py - miny) * s

    for n in top:
        n.x, n.y = tx(n.x, n.y)
        n.width *= s
        n.height *= s
    for n in diagram.nodes:
        if n.parent:
            n.x *= s
            n.y *= s
            n.width *= s
            n.height *= s
    for e in diagram.edges:
        if e.route:
            e.route = [tx(px, py) for px, py in e.route]
    return s, overflow


# =============================================================================
# Descomposición en hojas (multi-hoja)
# =============================================================================


def _children_map(diagram: Diagram) -> dict[str, list[Node]]:
    children: dict[str, list[Node]] = {}
    for n in diagram.nodes:
        if n.parent:
            children.setdefault(n.parent, []).append(n)
    return children


def _subtree_ids(root_id: str, children: dict[str, list[Node]]) -> set[str]:
    ids = {root_id}
    stack = [root_id]
    while stack:
        cur = stack.pop()
        for kid in children.get(cur, []):
            if kid.id not in ids:
                ids.add(kid.id)
                stack.append(kid.id)
    return ids


def _sub_diagram(diagram: Diagram, ids: set[str], name: str) -> Diagram:
    nodes = [n for n in diagram.nodes if n.id in ids]
    edges = [e for e in diagram.edges if e.source in ids and e.target in ids]
    return Diagram(name=name, nodes=nodes, edges=edges)


def _decompose(diagram: Diagram) -> list[tuple[str, Diagram]]:
    """Una hoja por boundary de nivel superior + una hoja 'Contexto'."""
    children = _children_map(diagram)
    top = [n for n in diagram.nodes if not n.parent]
    boundaries = [n for n in top if n.c4_type is C4Type.DEPLOYMENT_NODE]
    context = [n for n in top if n.c4_type is not C4Type.DEPLOYMENT_NODE]

    pages: list[tuple[str, Diagram]] = []
    if context:
        ids: set[str] = set()
        for n in context:
            ids |= _subtree_ids(n.id, children)
        pages.append(("Contexto", _sub_diagram(diagram, ids, "Contexto")))
    for b in boundaries:
        title = b.c4_name or b.id
        pages.append((title, _sub_diagram(diagram, _subtree_ids(b.id, children), title)))
    return pages


# =============================================================================
# Etiquetas C4
# =============================================================================


def _node_label(node: Node) -> str:
    t = node.c4_type
    if t is C4Type.DEPLOYMENT_NODE:
        return '<div style="text-align:left">%c4Name%</div><div style="text-align:left">[%c4Type%]</div>'
    parts = ["<b>%c4Name%</b>"]
    if t is C4Type.DATABASE:
        parts.append("<div>[Container: %c4Technology%]</div>" if node.c4_technology else "<div>[Database]</div>")
    elif t in (C4Type.CONTAINER, C4Type.COMPONENT) and node.c4_technology:
        parts.append("<div>[%c4Type%: %c4Technology%]</div>")
    else:
        parts.append("<div>[%c4Type%]</div>")
    if node.c4_description:
        parts.append("<br><div>%c4Description%</div>")
    return "".join(parts)


def _rel_label(desc: str, tech: str) -> str:
    parts = []
    if desc:
        parts.append('<div style="text-align:center"><b>%c4Description%</b></div>')
    if tech:
        parts.append('<div style="text-align:center">[%c4Technology%]</div>')
    return "".join(parts)


def _attr(value: str) -> str:
    return escape(value, {'"': "&quot;", "\n": "&#10;"})


# =============================================================================
# Serialización
# =============================================================================


def emit_c4(
    diagram: Diagram,
    c4_level: int,
    *,
    title_block: TitleBlock | None = None,
) -> EmitResult:
    """Emite el XML C4 completo (1 hoja, o varias si desborda y hay ≥2 boundaries)."""
    base_tb = title_block or TitleBlock(title=diagram.name)

    engine, motor = run_with_fallback(get_layout_engine(), diagram)  # fallback si ELK falla/timeout
    cw, ch = _content_bbox(diagram)
    _, _, area, _, _ = fit_page(cw, ch)
    boundaries = [n for n in diagram.nodes if not n.parent and n.c4_type is C4Type.DEPLOYMENT_NODE]
    needs_split = _scale_only(diagram, area) < _MIN_SCALE and len(boundaries) >= 2

    if not needs_split:
        block, scale, overflow, fmt, orientation = _emit_page(
            engine,
            diagram,
            base_tb,
            diagram_id=f"c4norm-{c4_level}",
            diagram_name=f"{diagram.name} (C4 N{c4_level})",
            tb_title=base_tb.title,
            sheet_n=1,
            sheet_m=1,
            relayout=False,
        )
        xml = "\n".join(['<mxfile host="c4norm" type="device">', *block, "</mxfile>", ""])
        return EmitResult(
            xml=xml,
            scale=scale_string(scale),
            overflow=overflow,
            engine=motor,
            sheet=fmt,
            orientation=orientation,
            sheets=1,
            cross_sheet_edges=0,
        )

    # Multi-hoja: una hoja por boundary + "Contexto".
    pages = _decompose(diagram)
    blocks: list[str] = []
    worst_scale = 1.0
    any_overflow = False
    drawn_edges = 0
    first_fmt, first_orientation = "A3", "landscape"
    for i, (title, sub) in enumerate(pages, start=1):
        block, scale, overflow, fmt, orientation = _emit_page(
            engine,
            sub,
            base_tb,
            diagram_id=f"c4norm-{c4_level}-{i}",
            diagram_name=f"{title} (C4 N{c4_level} · {i}/{len(pages)})",
            tb_title=title,
            sheet_n=i,
            sheet_m=len(pages),
            relayout=True,
        )
        blocks += block
        worst_scale = min(worst_scale, scale)
        any_overflow = any_overflow or overflow
        drawn_edges += sum(1 for e in sub.edges if e.source and e.target)
        if i == 1:
            first_fmt, first_orientation = fmt, orientation

    total_edges = sum(1 for e in diagram.edges if e.source and e.target)
    cross = max(0, total_edges - drawn_edges)
    xml = "\n".join(['<mxfile host="c4norm" type="device">', *blocks, "</mxfile>", ""])
    return EmitResult(
        xml=xml,
        scale=scale_string(worst_scale),
        overflow=any_overflow,
        engine=motor,
        sheet=first_fmt,
        orientation=first_orientation,
        sheets=len(pages),
        cross_sheet_edges=cross,
    )


def _emit_page(
    engine: LayoutEngine,
    sub: Diagram,
    base_tb: TitleBlock,
    *,
    diagram_id: str,
    diagram_name: str,
    tb_title: str,
    sheet_n: int,
    sheet_m: int,
    relayout: bool,
) -> tuple[list[str], float, bool, str, str]:
    """Diagrama (layout + ajuste + serialización) de UNA hoja. Devuelve (lines, escala, overflow, fmt, orientación)."""
    if relayout:
        engine.run(sub)

    cw, ch = _content_bbox(sub)
    page_w, page_h, area, fmt, orientation = fit_page(cw, ch)
    scale, overflow = _fit(sub, area)
    tb = replace(
        base_tb,
        title=tb_title,
        fmt=fmt,
        orientation=orientation,
        scale=scale_string(scale),
        sheet_n=sheet_n,
        sheet_m=sheet_m,
    )
    font = max(7, round(_BASE_FONT * scale))

    lines: list[str] = [
        f'  <diagram id="{_attr(diagram_id)}" name="{_attr(diagram_name)}">',
        f'    <mxGraphModel dx="1400" dy="900" grid="0" gridSize="10" guides="1" '
        f'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        f'pageWidth="{page_w}" pageHeight="{page_h}" math="0" shadow="0">',
        "      <root>",
        '        <mxCell id="0" />',
        '        <mxCell id="1" parent="0" />',
    ]
    lines += render_frame_and_title_block(page_w, page_h, tb)
    for node in sub.nodes:
        lines.append(_emit_node(node, font))
    abs_pos = _absolute_positions(sub)
    for edge in sub.edges:
        if edge.source and edge.target:
            lines.append(_emit_edge(edge, font, abs_pos))
    lines += ["      </root>", "    </mxGraphModel>", "  </diagram>"]
    return lines, scale, overflow, fmt, orientation


def _style_for(node: Node) -> str:
    spec = C4_SPEC[node.c4_type or C4Type.CONTAINER]
    if node.external and node.c4_type in (C4Type.SOFTWARE_SYSTEM, C4Type.DATABASE):
        return external_style(node.c4_type)
    return spec.cell_style


def _emit_node(node: Node, font: int) -> str:
    parent = node.parent or "1"
    style = _style_for(node) + f"fontSize={font};"
    label = _node_label(node)
    return (
        f'        <object placeholders="1" c4Name="{_attr(node.c4_name)}" '
        f'c4Type="{_attr((node.c4_type or C4Type.CONTAINER).value)}" '
        f'c4Technology="{_attr(node.c4_technology)}" c4Description="{_attr(node.c4_description)}" '
        f'label="{_attr(label)}" id="{_attr(node.id)}">\n'
        f'          <mxCell style="{_attr(style)}" parent="{_attr(parent)}" vertex="1">\n'
        f'            <mxGeometry x="{node.x:.0f}" y="{node.y:.0f}" '
        f'width="{node.width:.0f}" height="{node.height:.0f}" as="geometry" />\n'
        f"          </mxCell>\n"
        f"        </object>"
    )


def _absolute_positions(diagram: Diagram) -> dict[str, tuple[float, float, float, float]]:
    out: dict[str, tuple[float, float, float, float]] = {}
    in_progress: set[str] = set()  # protección contra ciclos A→parent=B, B→parent=A

    def resolve(node: Node) -> tuple[float, float, float, float]:
        if node.id in out:
            return out[node.id]
        if node.id in in_progress:
            # Ciclo detectado: devolver posición local sin acumular offset
            return (node.x, node.y, node.width, node.height)
        in_progress.add(node.id)
        ox, oy = 0.0, 0.0
        if node.parent:
            parent = diagram.node_by_id(node.parent)
            if parent is not None:
                px, py, _, _ = resolve(parent)
                ox, oy = px, py
        box = (ox + node.x, oy + node.y, node.width, node.height)
        out[node.id] = box
        in_progress.discard(node.id)
        return box

    for n in diagram.nodes:
        resolve(n)
    return out


def _exit_entry(src: tuple[float, float, float, float], tgt: tuple[float, float, float, float]) -> str:
    scx, scy = src[0] + src[2] / 2, src[1] + src[3] / 2
    tcx, tcy = tgt[0] + tgt[2] / 2, tgt[1] + tgt[3] / 2
    dx, dy = tcx - scx, tcy - scy
    if abs(dy) >= abs(dx):
        ex, ey, nx, ny = (0.5, 1, 0.5, 0) if dy > 0 else (0.5, 0, 0.5, 1)
    else:
        ex, ey, nx, ny = (1, 0.5, 0, 0.5) if dx > 0 else (0, 0.5, 1, 0.5)
    return f"exitX={ex};exitY={ey};exitDx=0;exitDy=0;entryX={nx};entryY={ny};entryDx=0;entryDy=0;"


def _emit_edge(edge, font: int, abs_pos: dict[str, tuple[float, float, float, float]]) -> str:  # noqa: ANN001
    label = _rel_label(edge.c4_description, edge.c4_technology)
    style = RELATIONSHIP_STYLE + f"fontSize={max(7, font - 1)};"

    if edge.route:
        # ELK entregó la ruta ortogonal (esquiva cajas): emitir como waypoints.
        points = "".join(f'<mxPoint x="{x:.0f}" y="{y:.0f}" />' for x, y in edge.route)
        geometry = (
            '            <mxGeometry relative="1" as="geometry">\n'
            f'              <Array as="points">{points}</Array>\n'
            "            </mxGeometry>"
        )
    else:
        if edge.source in abs_pos and edge.target in abs_pos:
            style += _exit_entry(abs_pos[edge.source], abs_pos[edge.target])
        geometry = '            <mxGeometry relative="1" as="geometry" />'

    return (
        f'        <object placeholders="1" c4Type="Relationship" '
        f'c4Technology="{_attr(edge.c4_technology)}" c4Description="{_attr(edge.c4_description)}" '
        f'label="{_attr(label)}" id="{_attr(edge.id)}">\n'
        f'          <mxCell style="{_attr(style)}" parent="1" '
        f'source="{_attr(edge.source or "")}" target="{_attr(edge.target or "")}" edge="1">\n'
        f"{geometry}\n"
        f"          </mxCell>\n"
        f"        </object>"
    )
