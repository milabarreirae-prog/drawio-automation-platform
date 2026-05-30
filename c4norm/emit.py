"""
Emisión C4 + hoja de ingeniería (ver docs/C4_NORMALIZER_DESIGN.md §4).

El layout lo provee un motor intercambiable (ELK real o fallback por capas).
Si el motor entrega rutas ortogonales (ELK), las líneas se dibujan con esos
quiebres (esquivan las cajas); si no, se enrutan por lado (peine). La página se
ajusta al contenido (1:1, mínimo blanco) con marco + cajetín ISO 7200.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from c4norm.layout import engine_name, get_layout_engine
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
) -> tuple[str, float, bool, str]:
    """Emite el XML C4 completo. Devuelve (xml, escala, overflow, motor)."""
    tb = title_block or TitleBlock(title=diagram.name)

    engine = get_layout_engine()
    engine.run(diagram)
    motor = engine_name(engine)

    cw, ch = _content_bbox(diagram)
    page_w, page_h, area, tb.fmt, tb.orientation = fit_page(cw, ch)
    scale, overflow = _fit(diagram, area)
    tb.scale = scale_string(scale)
    font = max(7, round(_BASE_FONT * scale))

    lines: list[str] = [
        '<mxfile host="c4norm" type="device">',
        f'  <diagram id="c4norm-{c4_level}" name="{_attr(diagram.name)} (C4 N{c4_level})">',
        f'    <mxGraphModel dx="1400" dy="900" grid="0" gridSize="10" guides="1" '
        f'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        f'pageWidth="{page_w}" pageHeight="{page_h}" math="0" shadow="0">',
        "      <root>",
        '        <mxCell id="0" />',
        '        <mxCell id="1" parent="0" />',
    ]
    lines += render_frame_and_title_block(page_w, page_h, tb)
    for node in diagram.nodes:
        lines.append(_emit_node(node, font))
    abs_pos = _absolute_positions(diagram)
    for edge in diagram.edges:
        if edge.source and edge.target:
            lines.append(_emit_edge(edge, font, abs_pos))

    lines += ["      </root>", "    </mxGraphModel>", "  </diagram>", "</mxfile>", ""]
    return "\n".join(lines), scale, overflow, motor


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

    def resolve(node: Node) -> tuple[float, float, float, float]:
        if node.id in out:
            return out[node.id]
        ox, oy = 0.0, 0.0
        if node.parent:
            parent = diagram.node_by_id(node.parent)
            if parent is not None:
                px, py, _, _ = resolve(parent)
                ox, oy = px, py
        box = (ox + node.x, oy + node.y, node.width, node.height)
        out[node.id] = box
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
