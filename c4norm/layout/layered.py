"""
Motor de layout por capas (Sugiyama simple) — fallback cuando ELK no está.

Árbol vertical centrado con reducción de cruces por baricentro y grilla interna
en los boundaries. Sin rutas explícitas (las líneas las rutea draw.io).
"""

from __future__ import annotations

import math

from c4norm.model import C4Type, Diagram, Node
from c4norm.sizing import auto_size

_GAP_X = 90
_GAP_Y = 120
_TITLE_H = 40
_GRID_PAD = 28
_CELL_PAD = 44


class LayeredLayout:
    """Motor de layout en árbol vertical (TB)."""

    def run(self, diagram: Diagram) -> None:
        children: dict[str, list[Node]] = {}
        for n in diagram.nodes:
            if n.parent:
                children.setdefault(n.parent, []).append(n)

        top = [n for n in diagram.nodes if not n.parent]
        for node in top:
            kids = children.get(node.id, [])
            if kids or node.c4_type is C4Type.DEPLOYMENT_NODE:
                self._grid(node, kids)
            else:
                auto_size(node)

        self._tree(top, diagram)

    def _grid(self, container: Node, kids: list[Node]) -> None:
        for k in kids:
            auto_size(k)
        if not kids:
            container.width, container.height = 360.0, 220.0
            return
        cols = max(1, math.ceil(math.sqrt(len(kids))))
        cell_w = max(k.width for k in kids) + _CELL_PAD
        cell_h = max(k.height for k in kids) + _CELL_PAD
        for i, k in enumerate(kids):
            r, c = divmod(i, cols)
            k.x = _GRID_PAD + c * cell_w
            k.y = _TITLE_H + _GRID_PAD + r * cell_h
        rows = math.ceil(len(kids) / cols)
        name_w = len(container.c4_name) * 7.4 + 40
        container.width = max(float(cols * cell_w + _GRID_PAD), name_w)
        container.height = float(_TITLE_H + rows * cell_h + _GRID_PAD)

    def _tree(self, nodes: list[Node], diagram: Diagram) -> None:
        if not nodes:
            return
        ids = {n.id for n in nodes}
        ancestor = self._ancestor_map(diagram, ids)
        adj = [
            (ancestor[e.source], ancestor[e.target])
            for e in diagram.edges
            if e.source in ancestor and e.target in ancestor
            and ancestor[e.source] != ancestor[e.target]
        ]

        layer = dict.fromkeys(ids, 0)
        for _ in range(len(ids)):
            changed = False
            for u, v in adj:
                if layer[v] < layer[u] + 1:
                    layer[v] = layer[u] + 1
                    changed = True
            if not changed:
                break

        order: dict[int, list[Node]] = {}
        for n in nodes:
            order.setdefault(layer[n.id], []).append(n)
        self._reduce_crossings(order, adj)

        row_w = {lvl: sum(n.width for n in row) + _GAP_X * (len(row) - 1) for lvl, row in order.items()}
        max_w = max(row_w.values()) if row_w else 0.0

        y_cursor = 0.0
        for lvl in sorted(order):
            row = order[lvl]
            x_cursor = (max_w - row_w[lvl]) / 2
            row_h = max(n.height for n in row)
            for n in row:
                n.x, n.y = x_cursor, y_cursor
                x_cursor += n.width + _GAP_X
            y_cursor += row_h + _GAP_Y

    @staticmethod
    def _reduce_crossings(order: dict[int, list[Node]], adj: list[tuple[str, str]]) -> None:
        up: dict[str, list[str]] = {}
        down: dict[str, list[str]] = {}
        for u, v in adj:
            down.setdefault(u, []).append(v)
            up.setdefault(v, []).append(u)

        layers = sorted(order)
        if len(layers) < 2:
            return

        def reorder(lvl: int, ref_lvl: int, neigh: dict[str, list[str]]) -> None:
            ref_index = {n.id: i for i, n in enumerate(order[ref_lvl])}
            current = {n.id: i for i, n in enumerate(order[lvl])}

            def bary(node: Node) -> float:
                refs = [ref_index[x] for x in neigh.get(node.id, []) if x in ref_index]
                return sum(refs) / len(refs) if refs else float(current[node.id])

            order[lvl].sort(key=bary)

        for sweep in range(4):
            if sweep % 2 == 0:
                for i in range(1, len(layers)):
                    reorder(layers[i], layers[i - 1], up)
            else:
                for i in range(len(layers) - 2, -1, -1):
                    reorder(layers[i], layers[i + 1], down)

    @staticmethod
    def _ancestor_map(diagram: Diagram, top_ids: set[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for n in diagram.nodes:
            cur, guard = n, 0
            while cur.parent and guard < 16:
                parent = diagram.node_by_id(cur.parent)
                if parent is None:
                    break
                cur, guard = parent, guard + 1
            out[n.id] = cur.id if cur.id in top_ids else n.id
        return out
