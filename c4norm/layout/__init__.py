"""
Motores de layout intercambiables.

  * ``ElkLayout``     — ELK real (elkjs/Node), ruteo ortogonal que esquiva cajas.
  * ``LayeredLayout`` — fallback en Python puro (sin dependencias).

``get_layout_engine()`` elige ELK si está disponible; si no, el fallback. Se
puede forzar con la variable de entorno ``C4NORM_LAYOUT`` = ``elk`` | ``layered``.
"""

from __future__ import annotations

import os
from typing import Protocol

from c4norm.layout.elk import ElkLayout
from c4norm.layout.layered import LayeredLayout
from c4norm.model import Diagram


class LayoutEngine(Protocol):
    def run(self, diagram: Diagram) -> None: ...


def get_layout_engine(prefer: str = "auto") -> LayoutEngine:
    mode = os.environ.get("C4NORM_LAYOUT", prefer).lower()
    if mode in ("elk", "auto"):
        elk = ElkLayout()
        if elk.available():
            return elk
        if mode == "elk":
            raise RuntimeError("Se forzó ELK pero no está disponible (falta Node/elkjs)")
    return LayeredLayout()


def engine_name(engine: LayoutEngine) -> str:
    return type(engine).__name__


__all__ = ["ElkLayout", "LayeredLayout", "LayoutEngine", "get_layout_engine", "engine_name"]
