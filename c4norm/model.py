"""
Modelo lógico de diagrama y definición canónica del estándar C4.

Separa la *lógica* del diagrama (nodos, aristas, contención, tipos C4) de su
*geometría*, que se descarta y recalcula. La tabla ``C4_SPEC`` codifica el
estándar C4 de draw.io (formas, colores y plantilla de etiqueta por tipo),
decodificado de la plantilla oficial (ver docs/C4_NORMALIZER_DESIGN.md §3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class C4Type(str, Enum):
    """Tipos C4 soportados (valores = atributo ``c4Type`` de draw.io)."""

    PERSON = "Person"
    SOFTWARE_SYSTEM = "Software System"
    CONTAINER = "Container"
    COMPONENT = "Component"
    DATABASE = "Database"
    DEPLOYMENT_NODE = "DeploymentNode"
    RELATIONSHIP = "Relationship"


@dataclass
class C4Style:
    """Estilo canónico de un tipo C4: forma/color + plantilla de etiqueta + tamaño."""

    cell_style: str
    label: str
    width: int
    height: int
    is_boundary: bool = False


# Paleta C4 canónica (de la plantilla oficial draw.io).
_PERSON = "#08427b"
_SYSTEM_INT = "#1168BD"
_SYSTEM_EXT = "#999999"
_SYSTEM_EXT_STROKE = "#8A8A8A"
_CONTAINER = "#438DD5"
_CONTAINER_STROKE = "#3C7FC0"
_COMPONENT = "#85BBF0"
_COMPONENT_STROKE = "#78A8D8"
_REL = "#707070"

# Plantillas de etiqueta con placeholders que draw.io expande (placeholders="1").
_LABEL_NAMED = "<b>%c4Name%</b><div>[%c4Type%]</div><br><div>%c4Description%</div>"
_LABEL_TECH = "<b>%c4Name%</b><div>[%c4Type%: %c4Technology%]</div><br><div>%c4Description%</div>"
_LABEL_DB = "<b>%c4Name%</b><div>[Container: %c4Technology%]</div><br><div>%c4Description%</div>"
_LABEL_NODE = (
    '<div style="text-align:left">%c4Name%</div>'
    '<div style="text-align:left">[%c4Type%]</div>'
)

_C4_POINTS = (
    "points=[[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0.25,0],[1,0.5,0],[1,0.75,0],"
    "[0.75,1,0],[0.5,1,0],[0.25,1,0],[0,0.75,0],[0,0.5,0],[0,0.25,0]];"
)


def _system_style(fill: str, stroke: str) -> str:
    return (
        f"rounded=1;whiteSpace=wrap;html=1;labelBackgroundColor=none;fillColor={fill};"
        f"fontColor=#ffffff;align=center;arcSize=10;strokeColor={stroke};metaEdit=1;{_C4_POINTS}"
    )


#: Estándar C4: tipo → estilo canónico.
C4_SPEC: dict[C4Type, C4Style] = {
    C4Type.PERSON: C4Style(
        cell_style=(
            f"html=1;dashed=0;whiteSpace=wrap;fillColor={_PERSON};strokeColor=none;"
            "fontColor=#ffffff;shape=mxgraph.c4.person;align=center;metaEdit=1;"
            "points=[[0.5,0,0],[1,0.5,0],[1,0.75,0],[0.75,1,0],[0.5,1,0],[0.25,1,0],[0,0.75,0],[0,0.5,0]];"
        ),
        label=_LABEL_NAMED,
        width=200,
        height=130,
    ),
    C4Type.SOFTWARE_SYSTEM: C4Style(_system_style(_SYSTEM_INT, _SYSTEM_INT), _LABEL_NAMED, 220, 120),
    C4Type.CONTAINER: C4Style(_system_style(_CONTAINER, _CONTAINER_STROKE), _LABEL_TECH, 220, 120),
    C4Type.COMPONENT: C4Style(_system_style(_COMPONENT, _COMPONENT_STROKE), _LABEL_TECH, 200, 110),
    C4Type.DATABASE: C4Style(
        cell_style=(
            f"shape=cylinder;whiteSpace=wrap;html=1;boundedLbl=1;rounded=1;labelBackgroundColor=none;"
            f"fillColor={_CONTAINER};fontColor=#ffffff;align=center;strokeColor={_CONTAINER_STROKE};"
            "metaEdit=1;arcSize=10;"
        ),
        label=_LABEL_DB,
        width=160,
        height=140,
    ),
    C4Type.DEPLOYMENT_NODE: C4Style(
        cell_style=(
            "rounded=1;whiteSpace=wrap;html=1;labelBackgroundColor=none;fillColor=#ffffff;"
            "fontColor=#000000;align=left;arcSize=5;strokeColor=#000000;verticalAlign=top;"
            "spacingTop=6;spacingLeft=8;metaEdit=1;container=1;collapsible=0;"
        ),
        label=_LABEL_NODE,
        width=320,
        height=240,
        is_boundary=True,
    ),
}

#: Estilo canónico de una arista C4 (Relationship).
RELATIONSHIP_STYLE = (
    "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;jettySize=auto;orthogonalLoop=1;"
    f"strokeColor={_REL};strokeWidth=2;fontColor={_REL};jumpStyle=none;dashed=1;endArrow=block;metaEdit=1;"
)
RELATIONSHIP_LABEL = (
    '<div style="text-align:center"><b>%c4Description%</b></div>'
    '<div style="text-align:center">[%c4Technology%]</div>'
)

#: Tamaños externos (sistema/DB externos usan gris).
EXTERNAL_FILL = _SYSTEM_EXT
EXTERNAL_STROKE = _SYSTEM_EXT_STROKE


def external_style(c4type: C4Type) -> str:
    """Variante en gris para sistemas/DB marcados como externos."""
    if c4type is C4Type.DATABASE:
        return (
            f"shape=cylinder;whiteSpace=wrap;html=1;boundedLbl=1;rounded=1;labelBackgroundColor=none;"
            f"fillColor={EXTERNAL_FILL};fontColor=#ffffff;align=center;strokeColor={EXTERNAL_STROKE};"
            "metaEdit=1;arcSize=10;"
        )
    return _system_style(EXTERNAL_FILL, EXTERNAL_STROKE)


@dataclass
class Node:
    """Un nodo del diagrama en el modelo lógico (geometría descartable)."""

    id: str
    raw_label: str = ""
    raw_style: dict[str, str] = field(default_factory=dict)
    shape: str = ""
    parent: str | None = None
    is_container_src: bool = False  # era swimlane/group/container en el origen
    x: float = 0.0
    y: float = 0.0
    width: float = 120.0
    height: float = 60.0
    explicit_c4_type: str | None = None  # c4Type provisto por la IA, si existe

    # Campos derivados (los completa el clasificador):
    c4_type: C4Type | None = None
    c4_name: str = ""
    c4_description: str = ""
    c4_technology: str = ""
    external: bool = False

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2


@dataclass
class Edge:
    """Una arista del modelo lógico."""

    id: str
    source: str | None = None
    target: str | None = None
    raw_label: str = ""
    source_point: tuple[float, float] | None = None
    target_point: tuple[float, float] | None = None

    # Derivados:
    c4_description: str = ""
    c4_technology: str = ""
    inferred: bool = False  # source/target reconstruidos por proximidad
    route: list[tuple[float, float]] = field(default_factory=list)  # bend points (absolutos)


@dataclass
class Diagram:
    """Modelo lógico completo de una página de diagrama."""

    name: str = "Diagram"
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    def node_by_id(self, node_id: str) -> Node | None:
        return next((n for n in self.nodes if n.id == node_id), None)
