"""
Anclaje de nodos flotantes ("nada flotando en el espacio").

Si el diagrama tiene boundaries (DeploymentNode) y hay nodos de infraestructura
(Container/Database) sueltos al nivel raíz, se agrupan dentro de un boundary
sintético "Red / Conectividad". Las personas y los sistemas externos SÍ pueden
quedar fuera de los boundaries (es C4 correcto), así que no se tocan.
"""

from __future__ import annotations

from c4norm.model import C4Type, Diagram, Node

_SYNTHETIC_ID = "c4norm-conectividad"


def ground_floating_nodes(diagram: Diagram) -> int:
    """Ancla nodos de infra flotantes en un boundary 'Red / Conectividad'.

    Devuelve cuántos nodos ancló (0 si no aplica).
    """
    has_boundary = any(n.c4_type is C4Type.DEPLOYMENT_NODE for n in diagram.nodes)
    if not has_boundary:
        return 0  # un flujo simple sin sitios no necesita anclaje

    floaters = [
        n
        for n in diagram.nodes
        if n.parent is None and n.c4_type in (C4Type.CONTAINER, C4Type.DATABASE)
    ]
    if not floaters:
        return 0

    zone = Node(
        id=_SYNTHETIC_ID,
        raw_label="Red / Conectividad",
        parent=None,
        is_container_src=True,
        c4_type=C4Type.DEPLOYMENT_NODE,
        c4_name="Red / Conectividad",
        c4_description="Zona de conectividad (anclaje de nodos de red/infra)",
    )
    for n in floaters:
        n.parent = zone.id
    diagram.nodes.insert(0, zone)
    return len(floaters)
