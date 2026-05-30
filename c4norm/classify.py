"""
Clasificación a C4 — el núcleo del motor (ver docs/C4_NORMALIZER_DESIGN.md §5).

Asigna a cada nodo su ``c4Type`` y extrae ``c4Name``/``c4Description``/
``c4Technology`` desde etiquetas sucias. Diseñado como interfaz intercambiable:

  * ``HeuristicClassifier``  — determinista, sin coste; respeta el ``c4Type`` que
    la IA ya haya emitido y, si no, lo infiere por forma + etiqueta + metadata.
  * ``LLMClassifier``        — stub pluggable (API tipo OpenAI, provider-agnóstico)
    para corregir diagramas fuera de estándar. Requisito futuro: NO implementado.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from c4norm.model import C4Type, Diagram, Edge, Node

# Pistas léxicas que sugieren "externo" (sistema/BD en gris).
_EXTERNAL_HINTS = ("externo", "external", "tercero", "proveedor externo", "sinacofi", "equifax", "servipag")
# Metadata que la IA mete en la etiqueta y que va a c4Description, no al nombre.
_META_PREFIXES = ("rol:", "confianza:", "estado cmdb:", "ip:", "host", "restricci")
# Pistas de tecnología frecuentes.
_TECH_HINTS = ("osb", "oracle", "java", "python", "json", "rest", "kafka", "html", "jdbc", "tcp", "19c", "11g", "12c")


def _split_label(raw_label: str) -> tuple[str, str, str]:
    """Devuelve (name, description, technology) desde la etiqueta limpia."""
    lines = [ln.strip() for ln in raw_label.split("\n") if ln.strip()]
    if not lines:
        return "", "", ""

    name = lines[0]
    rest = lines[1:]
    desc_parts: list[str] = []
    tech = ""
    for ln in rest:
        low = ln.lower()
        if any(low.startswith(p) for p in _META_PREFIXES):
            desc_parts.append(ln)
            continue
        if not tech and any(t in low for t in _TECH_HINTS) and len(ln) <= 40:
            tech = ln
            continue
        desc_parts.append(ln)
    return name, " · ".join(desc_parts), tech


class C4Classifier(ABC):
    """Interfaz de clasificación. ``classify`` muta el ``Diagram`` in-place."""

    @abstractmethod
    def classify(self, diagram: Diagram, c4_level: int) -> None: ...


class HeuristicClassifier(C4Classifier):
    """Clasificador determinista por forma + etiqueta + metadata + nivel."""

    def classify(self, diagram: Diagram, c4_level: int) -> None:
        for node in diagram.nodes:
            self._classify_node(node, c4_level)
        for edge in diagram.edges:
            self._classify_edge(edge)

    def _classify_node(self, node: Node, c4_level: int) -> None:
        node.c4_type = self._infer_type(node, c4_level)
        name, desc, tech = _split_label(node.raw_label)
        node.c4_name = name or node.id
        node.c4_description = desc
        node.c4_technology = tech
        low = node.raw_label.lower()
        node.external = any(h in low for h in _EXTERNAL_HINTS)

    def _infer_type(self, node: Node, c4_level: int) -> C4Type:
        # 1) Respetar el c4Type explícito que haya emitido la IA.
        if node.explicit_c4_type:
            try:
                return C4Type(node.explicit_c4_type)
            except ValueError:
                pass

        shape = node.shape.lower()
        style = (";".join(f"{k}={v}" for k, v in node.raw_style.items())).lower()

        # 2) Reglas por forma.
        if "person" in shape or "umlactor" in shape or "actor" in style:
            return C4Type.PERSON
        if "cylinder" in shape or shape.startswith("datastore"):
            return C4Type.DATABASE
        if node.is_container_src or "swimlane" in style:
            return C4Type.DEPLOYMENT_NODE
        if shape == "cloud":
            return C4Type.SOFTWARE_SYSTEM  # externo se marca aparte por etiqueta

        # 3) Caja genérica: depende del nivel C4 declarado.
        return C4Type.SOFTWARE_SYSTEM if c4_level <= 1 else C4Type.CONTAINER

    def _classify_edge(self, edge: Edge) -> None:
        text = edge.raw_label.strip()
        # Tecnología entre paréntesis o tras "—"; el resto es descripción.
        tech_match = re.search(r"\(([^)]+)\)|TCP\s*[\d/]+", text)
        if tech_match:
            edge.c4_technology = tech_match.group(0).strip("()")
            text = text.replace(tech_match.group(0), "").strip(" -–·")
        edge.c4_description = text


class LLMClassifier(C4Classifier):
    """
    Clasificador asistido por LLM (API tipo OpenAI, provider-agnóstico).

    STUB: requisito a futuro (corregir diagramas ya generados fuera de estándar).
    El proveedor se configurará por entorno y se invocará con un prompt que
    devuelva JSON validado contra schema. No implementado en el prototipo.
    """

    def __init__(self, provider: str = "openai", model: str | None = None) -> None:
        self.provider = provider
        self.model = model

    def classify(self, diagram: Diagram, c4_level: int) -> None:  # pragma: no cover
        raise NotImplementedError(
            "LLMClassifier es un stub pluggable para una fase futura. "
            "Usa HeuristicClassifier en el prototipo."
        )


def get_classifier(mode: str = "heuristic") -> C4Classifier:
    """Fábrica: ``heuristic`` | ``llm`` | ``auto`` (auto = heurístico por ahora)."""
    if mode == "llm":
        return LLMClassifier()
    return HeuristicClassifier()
