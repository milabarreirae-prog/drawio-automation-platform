"""
Diente de MINIMIZACIÓN de datos LeanIX (HU-ARQ-D2 · Ley 21.719 minimización/finalidad).

Contrato que muerde (Regla 123, observable independiente Ax-C4N-035): la query
``FACTSHEETS_QUERY`` sólo puede pedir campos escalares declarados en la allow-list
``FACTSHEETS_FIELD_PURPOSE`` (cada uno con propósito no vacío), y JAMÁS un campo de la
denylist de nombres de LeanIX conocidos por portar dato personal. El observable NO es el
builder (sería auto-espejo): se re-parsea el TEXTO de la query, independiente de cómo se
construyó. Fail-closed: añadir un escalar PII —aunque se le declare propósito— pone rojo.

Política acompañante: ``docs/POLITICA_DATOS_LEANIX.md`` (minimización + retención + licitud).
"""

from __future__ import annotations

import re

from c4norm.leanix import FACTSHEETS_FIELD_PURPOSE, FACTSHEETS_QUERY

#: Nombres de campo de FactSheet de LeanIX conocidos por portar (o poder portar) dato
#: personal o dato ajeno a un diagrama C4. Piso duro: NO se piden ni con propósito
#: declarado. Lista ampliable; su presencia en la query es SIEMPRE roja.
_PII_DENYLIST: frozenset[str] = frozenset(
    {
        "subscriptions",
        "user",
        "userName",
        "owner",
        "contact",
        "contacts",
        "email",
        "createdBy",
        "updatedBy",
        "responsible",
        "tags",
        "costs",
        "lifecycle",
        "documents",
        "comments",
    }
)


def _outer_scalar_leaves(query: str) -> set[str]:
    """Nombres de campo escalar solicitados DIRECTAMENTE en el ``node`` externo.

    Observable independiente del builder: recorta la región desde el primer ``node {``
    hasta el fragmento ``... on`` (los escalares de FactSheet se listan antes del
    fragmento embebido) y recolecta las líneas que son un identificador desnudo (sin
    ``{``, sin ``.``, sin ``:``). No confía en cómo se generó la query.
    """
    start = query.index("node {")
    fragment = query.index("... on", start)
    region = query[start + len("node {") : fragment]
    leaves: set[str] = set()
    for line in region.splitlines():
        token = line.strip()
        if not token or "{" in token or "}" in token or token.startswith("..."):
            continue
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
            leaves.add(token)
    return leaves


def _all_identifiers(query: str) -> set[str]:
    """Todos los identificadores que aparecen en la query (para el barrido de denylist)."""
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", query))


def test_scalar_leaves_equal_allowlist() -> None:
    """Los escalares del ``node`` externo son EXACTAMENTE las claves de la allow-list.

    Si el bloque de relaciones (u otra edición) introduce un escalar nuevo en el nivel
    externo sin pasar por la allow-list, o si la allow-list declara un campo que la query
    no pide, esto cae. Minimización = la query no pide más de lo declarado, ni menos.
    """
    assert _outer_scalar_leaves(FACTSHEETS_QUERY) == set(FACTSHEETS_FIELD_PURPOSE)


def test_every_allowlisted_field_declares_purpose() -> None:
    """Cada campo pedido justifica POR QUÉ c4norm lo necesita (finalidad, Ley 21.719)."""
    for field, purpose in FACTSHEETS_FIELD_PURPOSE.items():
        assert isinstance(purpose, str) and len(purpose.strip()) >= 12, (
            f"campo '{field}' sin propósito de finalidad declarado"
        )


def test_no_pii_field_is_requested() -> None:
    """MUERDE: ningún nombre de campo de la denylist PII aparece en la query.

    Piso duro de minimización: aunque alguien declare un propósito para 'owner' o
    'subscriptions' en la allow-list, seguiría rojo — estos campos no se piden a LeanIX
    desde c4norm. Cambiar esto exige revisar la política y la base de licitud (D2), no
    sólo tocar código.
    """
    leaked = _PII_DENYLIST & _all_identifiers(FACTSHEETS_QUERY)
    assert not leaked, f"la query pide campo(s) de la denylist PII: {sorted(leaked)}"


def test_allowlist_declares_no_pii_field() -> None:
    """La allow-list misma no puede legitimar un campo de la denylist PII."""
    leaked = _PII_DENYLIST & set(FACTSHEETS_FIELD_PURPOSE)
    assert not leaked, f"la allow-list declara campo(s) PII prohibido(s): {sorted(leaked)}"


def test_relations_pull_only_reference_ids() -> None:
    """Cada relación embebida sólo trae ``factSheet {{ id }}`` — una referencia de grafo,
    nunca un atributo de dato del extremo. Si una relación pidiera displayName/description
    u otro atributo, el barrido de escalares externos NO lo vería, pero SÍ lo delata que
    fuera de la allow-list sólo aparezcan tokens estructurales conocidos."""
    structural = {
        "query",
        "AllFactSheets",
        "allFactSheets",
        "edges",
        "node",
        "factSheet",
        "on",
        "Application",
        "id",
    }
    rel_tokens = {t for t in _all_identifiers(FACTSHEETS_QUERY) if t.startswith("rel")}
    # todo identificador es: una clave de allow-list, un token estructural, o un rel*.
    unexpected = _all_identifiers(FACTSHEETS_QUERY) - set(FACTSHEETS_FIELD_PURPOSE) - structural - rel_tokens
    assert not unexpected, f"identificador(es) inesperado(s) en la query: {sorted(unexpected)}"


#: HU-QA-D04 — testigo HARDCODEADO (humano, NO derivado de la allow-list) de los
#: escalares que ``inventory_to_diagram`` consume aguas abajo y cuya AUSENCIA de la
#: query degradaría el diagrama en silencio. Ancla contra REMOCIONES (H1 del 23º
#: recorrido QA): quitar un campo de la allow-list lo saca de la query construida y
#: rompe esta cota — el observable es el TEXTO de la query, no la allow-list que se audita.
_SCALARS_REQUIRED_DOWNSTREAM: frozenset[str] = frozenset(
    {
        "id",           # leanix.py: fs_id referenciable; sin él la relación cuelga
        "type",         # LEANIX_C4_MAP → C4Type; sin él no hay tipado
        "displayName",  # nombre visible del nodo C4
        "description",  # c4_description del nodo
    }
)


def test_query_requests_every_scalar_consumed_downstream() -> None:
    """MUERDE ante REMOCIÓN: cada escalar que inventory_to_diagram consume DEBE
    aparecer en el TEXTO de la query. Testigo independiente (lista hardcodeada) contra
    observable independiente (leaves re-parseadas del texto). Mutación que el 23º
    recorrido pidió fijar: quitar 'description' de FACTSHEETS_FIELD_PURPOSE → el builder
    lo saca de la query → esta cota cae (hoy: 0 rojos, era el hueco H1)."""
    leaves = _outer_scalar_leaves(FACTSHEETS_QUERY)
    faltantes = _SCALARS_REQUIRED_DOWNSTREAM - leaves
    assert not faltantes, f"la query NO pide escalar(es) consumido(s) aguas abajo: {sorted(faltantes)}"


def test_required_scalars_are_declared_in_allowlist() -> None:
    """Gemelo legítimo: los escalares requeridos son subconjunto de la allow-list, y
    AÑADIR un campo no-PII nuevo con propósito no rompe esta cota (subset se mantiene).
    Separa 'requerido por el consumidor' de 'declarado en la política' sin derivar uno
    del otro."""
    no_declarados = _SCALARS_REQUIRED_DOWNSTREAM - set(FACTSHEETS_FIELD_PURPOSE)
    assert not no_declarados, f"campo(s) consumido(s) no declarado(s) en la allow-list: {sorted(no_declarados)}"
