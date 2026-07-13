"""
Motor de layout ELK real (Eclipse Layout Kernel) vía ``elkjs`` sobre Node.

Construye un grafo ELK jerárquico (boundaries = nodos compuestos), lo envía al
runner Node persistente (``elk_runner.js``, un proceso reutilizado entre
diagramas — ver ``_PersistentElkProcess``), y aplica de vuelta posiciones +
rutas ortogonales de las aristas (que esquivan las cajas). Si Node/elkjs no
están disponibles, ``available()`` devuelve False y el orquestador usa el
fallback.
"""

from __future__ import annotations

import atexit
import contextlib
import json
import os
import queue
import shutil
import subprocess
import threading
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


class _PersistentElkProcess:
    """Proceso Node persistente que corre ``elk_runner.js`` en modo servidor.

    Se reutiliza entre diagramas (un ``python -m c4norm`` con multi-hoja, o
    varios requests de la API en el mismo proceso Python): evita pagar el
    arranque de Node en cada layout. Serializado con un lock — un solo grafo
    en vuelo a la vez, igual que antes (cada llamada era un proceso Node
    aparte, ahora es un turno del mismo proceso).
    """

    def __init__(self, node_bin: str) -> None:
        self._node_bin = node_bin
        self._proc: subprocess.Popen | None = None
        self._out_q: queue.Queue[bytes] = queue.Queue()
        self._lock = threading.Lock()

    def _start(self) -> None:
        # Cola nueva por arranque: el hilo lector del proceso anterior (si
        # sigue drenando su EOF tras un kill()) no debe escribir en la cola
        # que ya está sirviendo al proceso nuevo.
        self._out_q = queue.Queue()
        self._proc = subprocess.Popen(
            [self._node_bin, str(_RUNNER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        threading.Thread(target=self._pump_stdout, args=(self._proc, self._out_q), daemon=True).start()

    @staticmethod
    def _pump_stdout(proc: subprocess.Popen, out_q: queue.Queue[bytes]) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            out_q.put(line)
        out_q.put(b"")  # sentinela EOF: el proceso murió

    def _kill(self) -> None:
        if self._proc is not None:
            with contextlib.suppress(OSError):
                self._proc.kill()
            self._proc = None

    def send(self, graph: dict, timeout: float = 60.0) -> dict:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._start()
            proc = self._proc
            assert proc is not None and proc.stdin is not None
            try:
                proc.stdin.write(json.dumps(graph).encode("utf-8") + b"\n")
                proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._kill()
                raise RuntimeError(f"ELK (persistente): pipe roto al escribir: {exc}") from exc

            try:
                line = self._out_q.get(timeout=timeout)
            except queue.Empty:
                self._kill()
                raise RuntimeError("ELK (persistente) timeout (60 s): proceso Node tardó demasiado")
            if not line:
                stderr = b""
                if proc.stderr is not None:
                    stderr = proc.stderr.read() or b""
                self._kill()
                raise RuntimeError(f"ELK (persistente) murió: {stderr.decode('utf-8', 'replace')[:500]}")
            try:
                return json.loads(line)
            except json.JSONDecodeError as exc:
                self._kill()
                raise RuntimeError(f"ELK (persistente) respuesta inválida: {line[:200]!r}") from exc

    def shutdown(self) -> None:
        with self._lock:
            self._kill()


_process: _PersistentElkProcess | None = None
_process_lock = threading.Lock()


def _get_process(node_bin: str) -> _PersistentElkProcess:
    global _process
    with _process_lock:
        if _process is None:
            _process = _PersistentElkProcess(node_bin)
            atexit.register(_process.shutdown)
        return _process


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

        assert self.node_bin is not None
        graph = self._build_graph(diagram)
        result = _get_process(self.node_bin).send(graph, timeout=60.0)
        if "error" in result:
            raise RuntimeError(f"ELK falló: {str(result['error'])[:500]}")

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
