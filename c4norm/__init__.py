"""
c4norm — Motor de normalización de diagramas Draw.io al estándar C4.

Transforma XML de Draw.io crudo (típicamente generado por IA, en formato libre)
en XML conforme al estándar C4 de diagrams.net, listo para publicar en Confluence.

Pipeline (ver docs/C4_NORMALIZER_DESIGN.md):
    parse → modelo lógico → clasificar C4 → emitir C4 → layout → serializar

Punto de entrada de alto nivel: ``c4norm.normalize.normalize``.
"""

from __future__ import annotations

from c4norm.model import C4Type
from c4norm.normalize import NormalizeReport, normalize

__all__ = ["C4Type", "NormalizeReport", "normalize"]
