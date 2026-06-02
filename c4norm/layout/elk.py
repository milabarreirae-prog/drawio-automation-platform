"""
Motor de layout ELK real (Eclipse Layout Kernel) vía ``elkjs`` sobre Node.

Construye un grafo ELK jerárquico (boundaries = nodos compuestos), invoca el
runner Node (``elk_runner.js``), y aplica de vuelta posiciones + rutas
ortogonales de las aristas (que esquivan las cajas). Si Node/elkjs no están
disponibles, ``available()`` devuelve False y el orquestador usa el fallback.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from c4norm.model import C4Type, Diagram, Node
from c4norm.sizing import auto_size

_DIR = Path(__file__).parent
_RUNNER = _DIR / "elk_runner.js"
_NODE_MODULES = _DIR / "node_modules" / "elkjs"

_ROOT_OPTS = {
    "elk.algorithm": "layered",
    "elk.direction": "DOWN",
    "elk.edgeRouting": "ORTHOGONAL",
    "elk.hierarchyHandling": "INCLUDE_CHILDREN",
    "elk.layered.spacing.nodeNodeBetweenLayers": "80",
    "elk.spacing.nodeNode": "55",
    "elk.spacing.edgeNode": "25",
    "elk.layered.spacing.edgeNodeBetweenLayers": "25",
    "elk.padding": "[top=20,left=20,bottom=20,right=20]",
}
_BOUNDARY_OPTS = {
    "elk.padding": "[top=46,left=18,bottom=18,right=18]",
    "elk.spacing.nodeNode": "40",
}


def find_node_bin() -> str | None:
    """Localiza el ejecutable de Node: env, PATH, o instalación winget portable."""
    env = os.environ.get("C4NORM_NODE_BIN")
    if env and Path(env).exists():
        return env
    found = shutil.which("node")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA")
    if local:
        base = Path(local) / "Microsoft" / "WinGet" / "Packages"
        if base.exists():
            for exe in base.glob("OpenJS.NodeJS*/**/node.exe"):
                return str(exe)
    return None


class ElkLayout:
    """Motor de layout basado en ELK (elkjs) — ruteo ortogonal que esquiva cajas."""

    def __init__(self) -> None:
        self.node_bin = find_node_bin()

    def available(self) -> bool:
        return bool(self.node_bin) and _RUNNER.exists() and _NODE_MODULES.exists()

    # -- construcción del grafo ELK -------------------------------------------

    def _build_graph(self, diagram: Diagram) -> dict:
        children: dict[str, list[Node]] = {}
        for n in diagram.nodes:
            if n.parent:
                children.setdefault(n.parent, []).append(n)
        top = [n for n in diagram.nodes if not n.parent]
        ids = {n.id for n in diagram.nodes}

        edges = [
            {"id": e.id, "sources": [e.source], "targets": [e.target]}
            for e in diagram.edges
            if e.source in ids and e.target in ids
        ]
        return {
            "id": "root",
            "layoutOptions": _ROOT_OPTS,
            "children": [self._elk_node(n, children) for n in top],
            "edges": edges,
        }

    def _elk_node(self, node: Node, children: dict[str, list[Node]]) -> dict:
        kids = children.get(node.id, [])
        if node.c4_type is C4Type.DEPLOYMENT_NODE or kids:
            return {
                "id": node.id,
                "layoutOptions": dict(_BOUNDARY_OPTS),
                "children": [self._elk_node(k, children) for k in kids],
            }
        auto_size(node)
        return {"id": node.id, "width": round(node.width), "height": round(node.height)}

    # -- invocación + aplicación de resultados --------------------------------

    def run(self, diagram: Diagram) -> None:
        if not self.available():
            raise RuntimeError("ELK no disponible: falta Node o elkjs")

        graph = self._build_graph(diagram)
        proc = subprocess.run(
            [self.node_bin, str(_RUNNER)],
            input=json.dumps(graph).encode("utf-8"),
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"ELK falló: {proc.stderr.decode('utf-8', 'replace')[:500]}")
        result = json.loads(proc.stdout.decode("utf-8"))

        nodes_by_id = {n.id: n for n in diagram.nodes}
        edges_by_id = {e.id: e for e in diagram.edges}
        self._apply(result, 0.0, 0.0, nodes_by_id, edges_by_id)

    def _apply(
        self,
        elk_node: dict,
        ax: float,
        ay: float,
        nodes_by_id: dict[str, Node],
        edges_by_id: dict,
    ) -> None:
        # Aristas: bend points relativos a este contenedor → absolutos.
        for e in elk_node.get("edges", []):
            ed = edges_by_id.get(e.get("id"))
            if ed is None:
                continue
            pts: list[tuple[float, float]] = []
            for sec in e.get("sections", []):
                for bp in sec.get("bendPoints", []):
                    pts.append((ax + bp["x"], ay + bp["y"]))
            ed.route = pts

        # Nodos hijos: ELK da coords relativas al padre (igual que draw.io).
        for c in elk_node.get("children", []):
            nd = nodes_by_id.get(c["id"])
            cx, cy = float(c.get("x", 0.0)), float(c.get("y", 0.0))
            if nd is not None:
                nd.x, nd.y = cx, cy
                nd.width = float(c.get("width", nd.width))
                nd.height = float(c.get("height", nd.height))
            self._apply(c, ax + cx, ay + cy, nodes_by_id, edges_by_id)
