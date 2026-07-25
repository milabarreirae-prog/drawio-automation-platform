"""
Diente del genotipo federado ``gemelo_de_error`` (error-degradado-a-vacío).

R1 — "el vacío se afirma": un vacío devuelto sólo es legítimo si el mundo de
entrada era genuinamente vacío. Ninguna FALLA de un productor (parseo XML,
lectura de inventario, IO) puede aterrizar en la misma vista/resultado que un
vacío real. Litmus: "¿qué falla, al fallar, me trae a exactamente este mismo
vacío?" — la respuesta debe ser "ninguna".

R2 — ya es el núcleo constitucional de esta célula (``c4norm`` nunca inventa;
lo dudoso se marca "por validar") y no se repite aquí.

R3 — este archivo ES el guard-enumerador: la tabla ``_PRODUCERS`` abajo declara
todo productor falible conocido de c4norm/ que alimenta salida/artefactos, con
su par (entrada-vacía-legítima, entrada-corrupta) y la aserción de que ambas
son distinguibles. Los tests ``test_no_new_undeclared_producer_in_*`` obligan a
que un productor público NUEVO en ``parse.py``/``leanix.py`` se audite aquí
antes de que el guard vuelva a estar verde (si no se audita, el nombre falta en
el allowlist y el test es rojo).
"""

from __future__ import annotations

import inspect

import pytest
from lxml import etree

import c4norm.leanix as leanix_mod
import c4norm.parse as parse_mod
from c4norm.leanix import parse_factsheets
from c4norm.normalize import normalize
from c4norm.parse import parse_drawio

# =============================================================================
# R1 — parse.py::parse_drawio (el XML Draw.io crudo es nuestro "fetch"/"build")
# =============================================================================

# Vacío LEGÍTIMO: XML bien formado, sin ningún mxCell más allá de las raíces
# técnicas 0/1 que draw.io siempre emite. El motor no tiene por qué recuperarse
# de nada: parser.error_log queda vacío.
_XML_GENUINELY_EMPTY = '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel>'

# Corrupción real: un .drawio truncado a media escritura (descarga interrumpida,
# disco lleno, merge mal resuelto). Antes del diente, lxml con recover=True
# "recuperaba" un árbol parcial que descartaba justo el nodo cortado, dejando
# 0 mxCell reales — EXACTAMENTE la misma forma que el vacío legítimo de arriba.
_XML_TRUNCATED_MID_NODE = '<mxfile><diagram name="D"><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent'


def test_parse_drawio_genuinely_empty_is_not_an_error() -> None:
    """Control: el vacío se afirma. Un diagrama realmente vacío NO debe lanzar."""
    diagrams = parse_drawio(_XML_GENUINELY_EMPTY)
    assert len(diagrams) == 1
    assert diagrams[0].nodes == []
    assert diagrams[0].edges == []


def test_parse_drawio_truncated_xml_raises_distinguishably() -> None:
    """Diente: un .drawio truncado/corrupto DEBE lanzar, nunca degradar a vacío.

    Antes del guard en ``parse_drawio`` (revisar ``parser.error_log`` tras el
    parseo con ``recover=True``), esta llamada devolvía ``[Diagram(nodes=[],
    edges=[])]`` — bit a bit indistinguible del control de arriba. Si alguien
    revierte ese guard, este test vuelve a ponerse verde con datos vacíos en vez
    de rojo con excepción: esa reversión es la mutación que este diente muerde.
    """
    with pytest.raises(ValueError, match="corrupto o truncado"):
        parse_drawio(_XML_TRUNCATED_MID_NODE)


def test_mutation_proof_without_the_guard_corruption_looks_like_empty() -> None:
    """Prueba de que rojo-es-rojo: replica el camino de parseo SIN el guard nuevo
    (bare ``lxml`` con ``recover=True``, tal como estaba ``parse_drawio`` antes de
    este diente) y demuestra que, sin él, el XML truncado de arriba produce un
    árbol con CERO ``mxCell`` reales — la misma forma que el vacío legítimo.
    Esto es lo que ``parse_drawio`` ya NO permite tras el fix."""
    parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True, load_dtd=False)
    root = etree.fromstring(_XML_TRUNCATED_MID_NODE.encode("utf-8"), parser=parser)
    assert root is not None
    assert parser.error_log, "se esperaba que libxml2 tuviera que recuperarse de un error real"
    real_cells = [c for c in root.iter("mxCell") if c.get("id") not in ("0", "1")]
    assert real_cells == [], (
        "el árbol recuperado por libxml2 ya no contiene ningún mxCell real: "
        "sin el guard de error_log, esto es indistinguible del vacío legítimo"
    )


def test_parse_drawio_unparseable_garbage_raises() -> None:
    """Basura no-XML (root es None): ya lanzaba antes del diente; se preserva."""
    with pytest.raises(ValueError):
        parse_drawio("this is not xml at all !!! <<<")


def test_normalize_end_to_end_propagates_corruption_loudly() -> None:
    """El camino real (CLI/API pasan por ``normalize()``): la corrupción debe
    seguir siendo audible en el orquestador, no sólo en ``parse_drawio`` aislado."""
    with pytest.raises(ValueError, match="corrupto o truncado"):
        normalize(_XML_TRUNCATED_MID_NODE, c4_level=2)


def test_normalize_end_to_end_genuinely_empty_is_not_an_error() -> None:
    """Control gemelo del anterior: el vacío legítimo normaliza sin lanzar."""
    _xml_out, report = normalize(_XML_GENUINELY_EMPTY, c4_level=2)
    assert report.node_count == 0


# =============================================================================
# R1 — leanix.py::parse_factsheets (el inventario LeanIX es nuestro "fetch")
# =============================================================================

# Vacío LEGÍTIMO: forma GraphQL bien formada, tenant sin FactSheets.
_LEANIX_GENUINELY_EMPTY = {"data": {"allFactSheets": {"edges": []}}}

# Corrupción real: error GraphQL con 200 OK (token vencido, query rota) —
# `errors` presente y sin `data` útil. Antes del diente, `parse_factsheets`
# devolvía `[]` para CUALQUIER forma incompleta (`{}`, `{"data": {}}`, etc.),
# indistinguible del tenant vacío de arriba.
_LEANIX_GRAPHQL_ERROR = {"errors": [{"message": "Unauthorized"}]}


def test_leanix_genuinely_empty_inventory_is_not_an_error() -> None:
    assert parse_factsheets(_LEANIX_GENUINELY_EMPTY) == []


@pytest.mark.parametrize(
    "malformed_response",
    [
        {},
        {"data": {}},
        {"data": {"allFactSheets": {}}},
        {"data": {"allFactSheets": {"edges": None}}},
        _LEANIX_GRAPHQL_ERROR,
    ],
    ids=["sin-data", "sin-allFactSheets", "sin-edges", "edges-none", "graphql-errors"],
)
def test_leanix_malformed_response_raises_distinguishably(malformed_response: dict) -> None:
    """Diente: una respuesta LeanIX con forma inesperada (fallo de transporte/API)
    DEBE lanzar, nunca degradar al mismo ``[]`` que un inventario vacío real. El
    patrón "fail-safe" original (devolver ``[]`` ante cualquier forma incompleta)
    es exactamente la mutación que este test muerde: revertir el fix en
    ``parse_factsheets`` hace que estos casos vuelvan a devolver ``[]`` en vez de
    lanzar, y el test vuelve a ponerse verde con el bug presente — por eso se
    afirma la excepción explícitamente, no sólo la ausencia de crash."""
    with pytest.raises(ValueError):
        parse_factsheets(malformed_response)


# =============================================================================
# R3 — guard enumerador: ningún productor público nuevo se cuela sin auditar
# =============================================================================

# Productores falibles de parse.py auditados en este archivo (ambos con diente
# arriba). El resto de funciones públicas del módulo son transformaciones puras
# sobre el ``Diagram`` ya parseado (no leen bytes externos) o utilidades de
# texto sin modo de falla ambiguo entre "vacío" y "corrupto".
_PARSE_AUDITED_FALLIBLE = frozenset({"parse_drawio"})
_PARSE_AUDITED_NOT_APPLICABLE = frozenset(
    {"fix_mojibake", "label_to_text", "parse_style", "reconnect_orphan_edges", "repair_dangling_parents"}
)

# Productores falibles de leanix.py auditados en este archivo.
_LEANIX_AUDITED_FALLIBLE = frozenset({"parse_factsheets"})
_LEANIX_AUDITED_NOT_APPLICABLE = frozenset({"inventory_to_diagram", "leanix_to_c4"})
#: LeanIXClient es una clase (transporte inyectable): su modo de falla real
#: (``_http_post`` sin red) ya está cubierto por tests dedicados en
#: tests/test_leanix.py (falla explícita si no hay token/post inyectado) y
#: pragma: no cover en la rama de red real.


def _public_functions(module: object) -> set[str]:
    return {
        name
        for name, obj in inspect.getmembers(module)
        if not name.startswith("_") and inspect.isfunction(obj) and obj.__module__ == module.__name__
    }


def test_no_new_undeclared_producer_in_parse_module() -> None:
    """R3: si aparece una función pública nueva en ``c4norm/parse.py`` que no está
    en el allowlist de abajo, este test se pone ROJO — obliga a decidir y declarar
    explícitamente si es un productor falible (necesita diente R1) o no aplica,
    antes de que el guard vuelva a estar verde."""
    known = _PARSE_AUDITED_FALLIBLE | _PARSE_AUDITED_NOT_APPLICABLE
    actual = _public_functions(parse_mod)
    undeclared = actual - known
    assert not undeclared, (
        f"función(es) pública(s) nueva(s) sin auditar en c4norm/parse.py: {undeclared}. "
        "Añádelas a _PARSE_AUDITED_FALLIBLE (con diente R1 arriba) o a "
        "_PARSE_AUDITED_NOT_APPLICABLE (con justificación) en este archivo."
    )
    # Y lo inverso: nada declarado que ya no exista (allowlist podrida).
    assert not (known - actual), f"funciones declaradas que ya no existen en parse.py: {known - actual}"


def test_no_new_undeclared_producer_in_leanix_module() -> None:
    """R3, mismo guard para ``c4norm/leanix.py``."""
    known = _LEANIX_AUDITED_FALLIBLE | _LEANIX_AUDITED_NOT_APPLICABLE
    actual = _public_functions(leanix_mod)
    undeclared = actual - known
    assert not undeclared, (
        f"función(es) pública(s) nueva(s) sin auditar en c4norm/leanix.py: {undeclared}. "
        "Añádelas a _LEANIX_AUDITED_FALLIBLE (con diente R1 arriba) o a "
        "_LEANIX_AUDITED_NOT_APPLICABLE (con justificación) en este archivo."
    )
    assert not (known - actual), f"funciones declaradas que ya no existen en leanix.py: {known - actual}"
