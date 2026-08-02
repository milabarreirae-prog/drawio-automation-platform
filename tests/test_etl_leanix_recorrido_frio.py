"""
Recorrido en frío (cold-run) de la rebanada B-04 del ETL LeanIX.

Valida el camino REAL de producción contra el fixture grabado, sin red y sin
credenciales: fixture GraphQL → ``leanix_to_c4`` → XML C4 → ``XMLLinter``.
El DoD del green path es que el XML de salida pase el gate de compliance: nunca
BLOCKED; si el nivel es WARNING, el único contenido posible son stencils no
reconocidos ("por validar"), nunca una violación de tipado probada (Ax-C4N-016,
fail-closed).

También fija el invariante Ax-C4N-001 (el motor nunca inventa) sobre el fixture
real: el FactSheet ``techstack-legado`` (tipo ``TechnologyStack`` sin mapeo C4)
se conserva en el XML y se marca "por validar", no se descarta ni se le inventa
un tipo. Y el fixture grabado no porta credenciales (S4).
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from api.config import get_settings
from api.linting import XMLLinter
from api.schemas import ComplianceLevel
from c4norm.leanix import leanix_to_c4

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "leanix_falabella.json"


def _load_fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


# =============================================================================
# Green path — DoD: fixture → XML C4 → gate de compliance
# =============================================================================


def test_etl_recorrido_frio_fixture_a_xml_compliant() -> None:
    xml_out, warnings = leanix_to_c4(
        _load_fixture(), c4_level=1, name="Inventario Falabella (sintético)"
    )

    # XML bien formado (parser estándar, sin mezclar con lxml del linter).
    ET.fromstring(xml_out)  # noqa: S314 - XML propio, no de fuente externa

    # Los 4 nodos esperados del fixture están presentes en el XML.
    for expected_name in ("Portal Ventas", "Motor Pagos", "Gateway Pagos Externo", "BD Clientes"):
        assert expected_name in xml_out

    # Gate de compliance (DoD). Con los defaults actuales (allowed_stencils incluye
    # c4, colores deshabilitados, sin licencia ArchiMate) el resultado es COMPLIANT.
    # El DoD NO exige COMPLIANT literal: exige que nunca sea BLOCKED y que un WARNING
    # sólo pueda venir de stencils no reconocidos ("por validar"), nunca de una
    # violación probada de tipado/estilo.
    result = XMLLinter(get_settings()).full_validation(xml_out)

    assert result.xml_well_formed is True
    assert result.level != ComplianceLevel.BLOCKED
    assert not result.stencil_violations
    assert not result.color_violations
    for err in result.errors:
        assert "por validar" in err, f"hallazgo de linter inesperado (no 'por validar'): {err!r}"

    # El ETL no produce warnings inesperados: exactamente los 2 esperados
    # (1 tipo sin mapeo + 1 relación colgante), ambos "por validar".
    assert len(warnings) == 2


# =============================================================================
# Ax-C4N-001 — el motor nunca inventa (sobre el fixture real)
# =============================================================================


def test_etl_no_inventa_tipo_desconocido() -> None:
    xml_out, warnings = leanix_to_c4(
        _load_fixture(), c4_level=1, name="Inventario Falabella (sintético)"
    )

    # El nodo con tipo sin mapeo NO se descarta: su id y su nombre llegan al XML.
    assert "techstack-legado" in xml_out
    assert "Stack Legado XYZ" in xml_out

    # Y queda marcado "por validar", no silenciosamente inventado: la advertencia
    # declara el tipo LeanIX real y el mapeo neutro provisional (SOFTWARE_SYSTEM).
    assert any(
        "techstack-legado" in w and "TechnologyStack" in w and "por validar" in w for w in warnings
    ), f"falta advertencia 'por validar' para el tipo desconocido: {warnings}"


# =============================================================================
# S4 — el fixture grabado no porta credenciales
# =============================================================================


def test_etl_fixture_sin_credenciales_s4() -> None:
    raw = _FIXTURE_PATH.read_text(encoding="utf-8")

    for secret_fragment in ("sk-", "AKIA", "Bearer ", "Authorization", "password", "token="):
        assert secret_fragment not in raw, f"el fixture porta un patrón de credencial {secret_fragment!r}"
