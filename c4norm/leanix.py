"""
Ingesta de inventario LeanIX (FactSheets ya tipados) → ``Diagram`` C4 → XML C4.

LeanIX es un inventario YA TIPADO: cada FactSheet declara su ``type`` (Application,
ITComponent, DataObject, Provider, ...). Por eso NO reclasificamos desde etiqueta
cruda como hace ``classify.py``: mapeamos el tipo LeanIX → ``C4Type`` de forma
DETERMINISTA (``LEANIX_C4_MAP``) y construimos el ``Diagram`` ya tipado, análogo al
camino de ``textgen.py`` (genera → normaliza) pero sin paso de clasificación.

Axioma Ax-C4N-001 (el motor nunca inventa): un FactSheet de tipo desconocido NO se
descarta ni se le inventa un tipo C4 — se modela como ``SOFTWARE_SYSTEM`` (el más
neutro para contexto) marcado ``cmdb_status="por validar"`` y ``confidence="Baja"``,
con una advertencia legible. Una relación cuyo extremo no existe entre los nodos
conocidos NUNCA se dibuja colgada — se descarta con advertencia (dual de "nunca
inventar": "nunca colgar").

El transporte de red es inyectable (mismo patrón que ``TextExtractor.chat`` en
``textgen.py``): ``LeanIXClient`` recibe un ``post`` opcional; sin él, requiere un
token SSO federado (aranha-robots, patrón WF-002B). El camino HTTP real está marcado
``# pragma: no cover - requiere red`` y se prueba SÓLO contra el fixture grabado
(``tests/fixtures/leanix_falabella.json``), nunca contra la red real en tests.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from c4norm.emit import emit_c4
from c4norm.model import C4Type, Diagram, Edge, Node

if TYPE_CHECKING:
    from collections.abc import Callable

    from c4norm.sheet import TitleBlock

#: Mapeo DETERMINISTA tipo de FactSheet LeanIX → C4Type. No es heurístico: LeanIX ya
#: declara el tipo, aquí sólo se traduce al vocabulario C4.
LEANIX_C4_MAP: dict[str, C4Type] = {
    "Application": C4Type.SOFTWARE_SYSTEM,
    "ITComponent": C4Type.CONTAINER,
    "DataObject": C4Type.DATABASE,
    "BusinessCapability": C4Type.COMPONENT,
    "Provider": C4Type.SOFTWARE_SYSTEM,  # + external=True (ver inventory_to_diagram)
}

#: Tipos de FactSheet que NO son un nodo C4 (representan una relación, p.ej.
#: "Interface" modela una integración app↔app). Se excluyen del recuento de nodos
#: sin generar advertencia "por validar": es un caso CONOCIDO, no una omisión.
_NON_NODE_TYPES: frozenset[str] = frozenset({"Interface"})

#: Query GraphQL plausible sobre ``allFactSheets`` (sólo texto de referencia: no se
#: ejecuta contra red en tests, sólo el fixture grabado se usa para probar el parseo).
FACTSHEETS_QUERY: str = """\
query AllFactSheets {
  allFactSheets {
    edges {
      node {
        id
        type
        displayName
        description
        ... on Application {
          relApplicationToITComponent { edges { node { factSheet { id } } } }
          relApplicationToDataObject { edges { node { factSheet { id } } } }
          relApplicationToApplication { edges { node { factSheet { id } } } }
          relApplicationToProvider { edges { node { factSheet { id } } } }
        }
      }
    }
  }
}
"""


def parse_factsheets(response: dict) -> list[dict]:
    """Extrae la lista de FactSheets (``node``) de una respuesta GraphQL ``allFactSheets``.

    R1 (el vacío se afirma): un ``allFactSheets.edges`` bien formado pero vacío
    (``[]``) es un inventario genuinamente vacío y SÍ devuelve ``[]`` en silencio.
    Pero una respuesta con la FORMA equivocada (sin ``data``, error GraphQL en
    ``errors``, ``allFactSheets`` o ``edges`` ausentes/con tipo incorrecto) es un
    FALLO del transporte/productor (token vencido, endpoint equivocado, GraphQL
    devolvió error con 200 OK) — antes colapsaba al mismo ``[]`` que el inventario
    vacío real (patrón fail-safe original del repo); ahora se distingue con una
    excepción, porque ninguna falla del productor debe aterrizar en la misma vista
    que un vacío legítimo.

    Registros individuales corruptos DENTRO de un ``edges`` ya bien formado (p.ej.
    ``{"node": None}``) sí se descartan en silencio: son un caso "por validar" de
    dato individual, no un fallo estructural de la respuesta completa.
    """
    if not isinstance(response, dict):
        raise ValueError(f"Respuesta LeanIX no es un objeto JSON: {type(response).__name__}")
    if response.get("errors"):
        raise ValueError(f"LeanIX devolvió error(es) GraphQL: {response['errors']}")
    if "data" not in response or not isinstance(response["data"], dict):
        raise ValueError("Respuesta LeanIX con forma inesperada: falta 'data' (fallo del productor)")
    data = response["data"]
    if "allFactSheets" not in data or not isinstance(data["allFactSheets"], dict):
        raise ValueError(
            "Respuesta LeanIX con forma inesperada: falta 'data.allFactSheets' (fallo del productor)"
        )
    all_fs = data["allFactSheets"]
    if "edges" not in all_fs or not isinstance(all_fs["edges"], list):
        raise ValueError(
            "Respuesta LeanIX con forma inesperada: falta 'data.allFactSheets.edges' como lista "
            "(fallo del productor)"
        )
    out: list[dict] = []
    for item in all_fs["edges"]:
        if not isinstance(item, dict):
            continue
        node = item.get("node")
        if isinstance(node, dict):
            out.append(node)
    return out


def _relation_targets(raw: dict) -> list[str]:
    """Ids de FactSheet apuntados por cualquier campo ``rel*`` embebido en ``raw``.

    LeanIX embebe relaciones bajo claves ``relXxxToYyy`` con forma
    ``{"edges": [{"node": {"factSheet": {"id": "..."}}}]}``. Se procesa CUALQUIER
    clave que siga ese patrón (no una lista cerrada) para no perder relaciones que
    el fixture declare con otro nombre de campo estándar de LeanIX.

    ``relToParent`` se EXCLUYE aquí a propósito: aunque empieza con ``rel`` (y por
    tanto calzaría con el patrón), declara contención jerárquica, no una relación
    de arquitectura — se procesa aparte en ``_declared_parent`` para no dibujar una
    flecha espuria padre→hijo.
    """
    targets: list[str] = []
    for key, value in raw.items():
        if key == "relToParent" or not key.startswith("rel") or not isinstance(value, dict):
            continue
        rel_edges = value.get("edges")
        if not isinstance(rel_edges, list):
            continue
        for rel_edge in rel_edges:
            if not isinstance(rel_edge, dict):
                continue
            rel_node = rel_edge.get("node")
            fs_ref = rel_node.get("factSheet") if isinstance(rel_node, dict) else None
            tgt_id = fs_ref.get("id") if isinstance(fs_ref, dict) else None
            if isinstance(tgt_id, str) and tgt_id:
                targets.append(tgt_id)
    return targets


def _declared_parent(raw: dict) -> str | None:
    """Id del FactSheet padre DECLARADO por ``raw`` en su campo ``relToParent``, o
    ``None`` si no lo declara.

    Misma forma embebida ``{"edges": [{"node": {"factSheet": {"id": "..."}}}]}``
    que el resto de campos ``rel*``. Ax-C4N-001: la agrupación SÓLO viene de este
    campo declarado — nunca se infiere de nombres, prefijos ni otra heurística. Se
    toma el primer edge declarado (un FactSheet tiene a lo sumo un padre en un
    árbol de contención).
    """
    value = raw.get("relToParent")
    if not isinstance(value, dict):
        return None
    rel_edges = value.get("edges")
    if not isinstance(rel_edges, list):
        return None
    for rel_edge in rel_edges:
        if not isinstance(rel_edge, dict):
            continue
        rel_node = rel_edge.get("node")
        fs_ref = rel_node.get("factSheet") if isinstance(rel_node, dict) else None
        tgt_id = fs_ref.get("id") if isinstance(fs_ref, dict) else None
        if isinstance(tgt_id, str) and tgt_id:
            return tgt_id
    return None


def inventory_to_diagram(
    response: dict, *, name: str = "Inventario LeanIX"
) -> tuple[Diagram, list[str]]:
    """Construye el ``Diagram`` C4 tipado a partir de una respuesta ``allFactSheets``.

    Devuelve ``(diagram, advertencias)``. Las advertencias son texto legible "por
    validar": tipos LeanIX sin mapeo C4, relaciones descartadas por apuntar a un
    extremo inexistente, y jerarquía declarada (``relToParent``) inconsistente
    (padre inexistente o autorreferencia). El motor nunca inventa (Ax-C4N-001): lo
    dudoso se marca, nunca se calla ni se adivina.

    La jerarquía SÓLO sale de ``relToParent`` (nunca se infiere de nombres o
    prefijos): todo FactSheet que sea padre declarado de al menos un hijo se
    PROMUEVE a boundary (``C4Type.DEPLOYMENT_NODE``), lo que activa el camino
    multi-hoja de ``emit.py`` (una hoja por boundary de nivel superior).
    """
    raw_nodes = parse_factsheets(response)
    warnings: list[str] = []
    diagram = Diagram(name=name)

    known_ids: set[str] = set()
    kept_raw: list[dict] = []
    for raw in raw_nodes:
        fs_type = raw.get("type", "")
        if fs_type in _NON_NODE_TYPES:
            continue
        fs_id = raw.get("id")
        if not isinstance(fs_id, str) or not fs_id:
            continue  # sin id no es referenciable; se descarta sin inventar uno
        kept_raw.append(raw)
        known_ids.add(fs_id)

    for raw in kept_raw:
        fs_id = raw["id"]
        fs_type = raw.get("type", "")
        c4_name = raw.get("displayName") or raw.get("name") or fs_id
        node = Node(
            id=fs_id,
            c4_name=str(c4_name),
            c4_description=str(raw.get("description") or ""),
        )
        if fs_type in LEANIX_C4_MAP:
            node.c4_type = LEANIX_C4_MAP[fs_type]
            node.external = fs_type == "Provider" or bool(raw.get("external"))
        else:
            node.c4_type = C4Type.SOFTWARE_SYSTEM
            node.cmdb_status = "por validar"
            node.confidence = "Baja"
            warnings.append(
                f"FactSheet {fs_id} tipo LeanIX '{fs_type}' sin mapeo C4 → SOFTWARE_SYSTEM por validar"
            )
        diagram.nodes.append(node)

    for raw in kept_raw:
        src_id = raw["id"]
        for tgt_id in _relation_targets(raw):
            if tgt_id not in known_ids:
                warnings.append(f"relación {src_id}->{tgt_id} descarta: extremo inexistente")
                continue
            diagram.edges.append(Edge(id=f"rel-{src_id}-{tgt_id}", source=src_id, target=tgt_id))

    # Jerarquía declarada (Ax-C4N-001: nunca inventar = nunca perder). La agrupación
    # SÓLO viene de ``relToParent`` — nunca se infiere de nombres ni prefijos. Un
    # padre inexistente entre los FactSheets conservados no se inventa: el nodo
    # queda sin agrupar y se advierte, nunca se descarta.
    nodes_by_id = {n.id: n for n in diagram.nodes}
    child_counts: dict[str, int] = {}
    for raw in kept_raw:
        fs_id = raw["id"]
        parent_id = _declared_parent(raw)
        if parent_id is None:
            continue
        if parent_id == fs_id:
            warnings.append(f"FactSheet {fs_id} declara parent a si mismo → ignorado")
            continue
        if parent_id not in known_ids:
            warnings.append(f"FactSheet {fs_id} declara parent {parent_id} inexistente → sin agrupar")
            continue
        nodes_by_id[fs_id].parent = parent_id
        child_counts[parent_id] = child_counts.get(parent_id, 0) + 1

    # Todo FactSheet que sea padre declarado de al menos un hijo se promueve a
    # boundary: nunca silencioso, cada promoción queda advertida (auditable).
    for parent_id, n in child_counts.items():
        parent_node = nodes_by_id[parent_id]
        parent_node.c4_type = C4Type.DEPLOYMENT_NODE
        warnings.append(f"FactSheet {parent_node.id} promovido a boundary (agrupa {n} hijos declarados)")

    return diagram, warnings


class LeanIXClient:
    """Cliente LeanIX con transporte inyectable (mismo patrón que ``TextExtractor``).

    Sin ``post`` inyectado, el único camino válido es SSO federado real (token
    aranha-robots, patrón WF-002B): sin token, falla explícito en vez de degradar
    silenciosamente. Con ``post`` inyectado (tests / fixture grabado), nunca toca red.
    """

    def __init__(
        self,
        *,
        post: Callable[[str], dict] | None = None,
        base_url: str = "",
        token: str = "",
    ) -> None:
        self.base_url = base_url or os.environ.get("C4NORM_LEANIX_BASE_URL", "")
        self.token = token if token else os.environ.get("C4NORM_LEANIX_TOKEN", "")
        self._post = post

    def fetch_inventory(self, query: str) -> dict:
        """Ejecuta ``query`` contra LeanIX (o el ``post`` inyectado) y devuelve el JSON crudo."""
        if self._post is not None:
            return self._post(query)
        if not self.token:
            raise ValueError(
                "LeanIXClient requiere token SSO federado (aranha-robots, patrón WF-002B) "
                "o un 'post' inyectado para fixture."
            )
        return self._http_post(query)

    def _http_post(self, query: str) -> dict:  # pragma: no cover - requiere red
        import httpx

        try:
            response = httpx.post(
                f"{self.base_url.rstrip('/')}/services/pathfinder/v1/graphql",
                headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
                json={"query": query},
                timeout=60,
            )
        except httpx.RequestError as exc:
            raise ValueError(f"LeanIXClient: error de red al contactar {self.base_url}: {exc}") from exc
        if not response.is_success:
            raise ValueError(f"LeanIXClient: LeanIX devolvió {response.status_code}: {response.text[:300]}")
        return dict(response.json())


def leanix_to_c4(
    response: dict,
    *,
    c4_level: int,
    name: str,
    title_block: TitleBlock | None = None,
) -> tuple[str, list[str]]:
    """Camino de conveniencia end-to-end: inventario LeanIX → XML C4 + advertencias."""
    diagram, warnings = inventory_to_diagram(response, name=name)
    result = emit_c4(diagram, c4_level, title_block=title_block)
    return result.xml, warnings
