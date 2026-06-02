"""
Dimensionado de cajas al texto (compartido por los motores de layout).

Cada caja se ajusta a su contenido; la persona conserva silueta vertical.
Los boundaries (DeploymentNode) se dimensionan por su contenido en el motor de
layout, no aquí.
"""

from __future__ import annotations

import math

from c4norm.model import C4Type, Node

_CHAR_W = 7.4
_LINE_H = 18
_MIN_W, _MAX_W = 160, 300
_MIN_H = 70


def auto_size(node: Node) -> None:
    """Ajusta width/height de un nodo hoja a su contenido."""
    if node.c4_type is C4Type.DEPLOYMENT_NODE:
        return

    name = node.c4_name or node.id
    type_line = f"[{(node.c4_type or C4Type.CONTAINER).value}]"
    head_len = max(len(name), len(type_line))
    width = min(_MAX_W, max(_MIN_W, head_len * _CHAR_W + 28))
    cpl = max(8, int((width - 24) / 6.8))
    desc_lines = math.ceil(len(node.c4_description) / cpl) if node.c4_description else 0

    if node.c4_type is C4Type.PERSON:
        node.width = float(min(200, max(150, len(name) * _CHAR_W + 20)))
        node.height = float(max(160, (2 + desc_lines) * _LINE_H + 60))
        return

    lines = 2 + desc_lines
    height = max(_MIN_H, lines * _LINE_H + 24)
    if node.c4_type is C4Type.DATABASE:
        height += 18
    node.width, node.height = float(width), float(height)
