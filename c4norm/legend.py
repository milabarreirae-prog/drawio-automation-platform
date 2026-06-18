"""
Leyenda C4 estándar generada por el motor.

La leyenda del diagrama crudo suele explicar una convención de color propia
(p.ej. azul=negocio, verde=crítico, rojo=legacy). Tras normalizar, c4norm
recolorea por **tipo C4**, así que esa leyenda queda inválida. Cuando el
enriquecimiento está activo, se descarta la leyenda original y se genera esta
**clave C4 limpia y estándar** con los tipos realmente presentes: una fila por
tipo (con su color/forma canónica) + relación.
"""

from __future__ import annotations

from c4norm.model import Annotation, C4Type, Diagram

# Orden canónico y rótulo en español de cada tipo C4.
_LEGEND_ROWS: list[tuple[C4Type, str, str, str]] = [
    # (tipo, fill, fontColor, rótulo)
    (C4Type.PERSON, "#08427b", "#ffffff", "Persona / actor"),
    (C4Type.SOFTWARE_SYSTEM, "#1168BD", "#ffffff", "Sistema de software"),
    (C4Type.CONTAINER, "#438DD5", "#ffffff", "Contenedor"),
    (C4Type.COMPONENT, "#85BBF0", "#000000", "Componente"),
    (C4Type.DATABASE, "#438DD5", "#ffffff", "Almacén de datos"),
    (C4Type.DEPLOYMENT_NODE, "#ffffff", "#000000", "Zona / nodo de despliegue"),
]

_ROW_W = 210.0
_ROW_H = 28.0
_GAP = 6.0
_HEADER_H = 24.0


def build_standard_legend(diagram: Diagram, anchor_x: float, anchor_y: float) -> list[Annotation]:
    """Construye la leyenda C4 para los tipos presentes, anclada en (anchor_x, anchor_y).

    Devuelve celdas de anotación (``kind="legend"``) con coordenadas absolutas; el
    emisor las reubica con el resto de anotaciones en la banda bajo el diagrama.
    """
    present = {n.c4_type for n in diagram.nodes if n.c4_type is not None}
    rows = [r for r in _LEGEND_ROWS if r[0] in present]
    if not rows:
        return []

    cells: list[Annotation] = []
    n_slots = len(rows) + (1 if any(e.source and e.target for e in diagram.edges) else 0)
    total_h = _HEADER_H + n_slots * (_ROW_H + _GAP) + 8

    # Marco contenedor (se dibuja primero, debajo de las filas).
    cells.append(
        Annotation(
            id="legend-frame",
            value="",
            style="rounded=1;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#666666;dashed=1;",
            kind="legend",
            x=anchor_x - 10,
            y=anchor_y - 10,
            width=_ROW_W + 20,
            height=total_h + 12,
        )
    )
    # Encabezado.
    cells.append(
        Annotation(
            id="legend-title",
            value="<b>Leyenda (C4)</b>",
            style="text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;fontSize=13;",
            kind="legend",
            x=anchor_x,
            y=anchor_y,
            width=_ROW_W,
            height=_HEADER_H,
        )
    )
    y = anchor_y + _HEADER_H + _GAP
    for i, (ctype, fill, font, label) in enumerate(rows):
        dashed = ";dashed=1;strokeColor=#000000" if ctype is C4Type.DEPLOYMENT_NODE else ""
        cells.append(
            Annotation(
                id=f"legend-{ctype.value.replace(' ', '_').lower()}",
                value=label,
                style=(
                    f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};fontColor={font};"
                    f"align=left;spacingLeft=10;fontSize=12{dashed}"
                ),
                kind="legend",
                x=anchor_x,
                y=y + i * (_ROW_H + _GAP),
                width=_ROW_W,
                height=_ROW_H,
            )
        )

    # Fila de relación (si hay aristas).
    if any(e.source and e.target for e in diagram.edges):
        cells.append(
            Annotation(
                id="legend-relationship",
                value="→ Relación",
                style="text;html=1;strokeColor=none;fillColor=none;align=left;spacingLeft=10;fontSize=12;",
                kind="legend",
                x=anchor_x,
                y=y + len(rows) * (_ROW_H + _GAP),
                width=_ROW_W,
                height=_ROW_H,
            )
        )
    return cells
