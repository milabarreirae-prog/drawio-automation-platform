"""Tests para scripts/verificar_trazabilidad_requerimientos.py.

Este verificador detecta requerimientos (RF/RNF) en `wiki/REQUERIMIENTOS_v1.md` cuyas
referencias a tests no resuelven a nada real en disco (huérfanos), a diferencia de los
requerimientos marcados explícitamente como Futuro/EN DESARROLLO (pendientes declarados,
que no cuentan como huérfanos).

Test 1 corre el verificador REAL como subproceso contra el doc REAL del repo y afirma el
estado HONESTO observado (no maquillado): a fecha de escritura de este test, el doc real
tiene 16 requerimientos (RF-001..RF-011, RNF-001..RNF-005), de los cuales 2 son pendientes
declarados (RF-011, RNF-005) y **3 salen huérfanos**: RF-008 (cero referencias a tests en
su sección — solo cita "B-01a/B-01b tests" en prosa, sin ningún `test_*.py` real), RNF-002
(cita `tests/test_*.py` con un glob literal que nunca matchea el patrón de node-id de
pytest) y RNF-003 (cita `test_audit_perf.py::test_cli_latency`, pero esa función no existe
en `tests/test_audit_perf.py` — ese archivo real contiene tests de concurrencia LLM, no de
latencia). Si en el futuro se corrige el doc y estos tres dejan de ser huérfanos, este test
debe actualizarse para reflejar el nuevo estado honesto (no se debe fijar en verde a
ciegas).

Test 2 es el diente mutation-proof: fabrica un requerimiento con una referencia fantasma,
confirma que el verificador lo marca huérfano, y luego confirma que con una referencia real
deja de serlo — probando que el verificador distingue evidencia real de una cita fantasma
(no está siempre-verde ni siempre-rojo).

Test 3 confirma que un requerimiento marcado (Futuro)/(EN DESARROLLO) sin tests NO se
reporta como huérfano.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.verificar_trazabilidad_requerimientos import (
    DOC_PATH_DEFAULT,
    REPO_ROOT,
    analizar,
    verificar,
)

TESTS_DIR = Path(__file__).resolve().parent
REAL_EXISTING_TEST_REF = "tests/test_c4norm.py::test_all_levels_emit_valid_xml"


def test_real_doc_hoy_tiene_exactamente_tres_huerfanos() -> None:
    """Estado honesto observado corriendo el verificador contra el doc real (ver docstring
    del módulo): RF-008, RNF-002 y RNF-003 son huérfanos hoy; el resto no."""
    proceso = subprocess.run(
        [sys.executable, "scripts/verificar_trazabilidad_requerimientos.py"],
        capture_output=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
    )

    assert proceso.returncode == 1, proceso.stdout
    assert "RF-008" in proceso.stdout
    assert "RNF-002" in proceso.stdout
    assert "RNF-003" in proceso.stdout
    assert "3 requerimiento(s) hu" in proceso.stdout  # "huérfano(s)" (acento omitido a propósito)

    # Confirmación independiente vía la función importable, contra el mismo doc real.
    resultado = analizar(DOC_PATH_DEFAULT, REPO_ROOT / "tests")
    huerfanos_ids = {h.req_id for h in resultado.huerfanos}
    assert huerfanos_ids == {"RF-008", "RNF-002", "RNF-003"}
    assert set(resultado.pendientes) == {"RF-011", "RNF-005"}


def test_referencia_fantasma_sale_huerfano_y_referencia_real_no(tmp_path: Path) -> None:
    """Diente mutation-proof: una referencia a un test que no existe marca el requerimiento
    como huérfano; cambiar esa misma referencia por un test real hace que deje de serlo."""
    # Confirma primero que el test "real" que vamos a usar de contraste efectivamente existe.
    assert (TESTS_DIR / "test_c4norm.py").is_file()
    assert "test_all_levels_emit_valid_xml" in (TESTS_DIR / "test_c4norm.py").read_text(encoding="utf-8")

    doc_fantasma = tmp_path / "requerimientos_fantasma.md"
    doc_fantasma.write_text(
        "### RF-999: requerimiento fabricado\n\n"
        "**Pruebas verificadas**\n"
        "- `tests/test_no_existe_jamas.py::test_fantasma`\n\n"
        "**Estado:** CUMPLIDO\n",
        encoding="utf-8",
    )

    huerfanos = verificar(doc_fantasma, TESTS_DIR)
    assert any(h.req_id == "RF-999" for h in huerfanos), huerfanos

    doc_real = tmp_path / "requerimientos_real.md"
    doc_real.write_text(
        "### RF-999: requerimiento fabricado\n\n"
        "**Pruebas verificadas**\n"
        f"- `{REAL_EXISTING_TEST_REF}`\n\n"
        "**Estado:** CUMPLIDO\n",
        encoding="utf-8",
    )

    huerfanos = verificar(doc_real, TESTS_DIR)
    assert not any(h.req_id == "RF-999" for h in huerfanos), huerfanos


def test_requerimiento_pendiente_declarado_sin_tests_no_es_huerfano(tmp_path: Path) -> None:
    """Un RF/RNF marcado (Futuro) o (EN DESARROLLO) sin ninguna referencia a tests va a
    'pendientes declarados', nunca a huérfanos."""
    doc = tmp_path / "requerimientos_pendientes.md"
    doc.write_text(
        "### RF-998 (EN DESARROLLO): requerimiento futuro sin tests\n\n"
        "**Descripción**\n"
        "Placeholder sin ninguna referencia a tests todavía.\n\n"
        "**Estado:** EN DESARROLLO\n\n"
        "---\n\n"
        "### RNF-997 (Futuro): otro requerimiento aplazado\n\n"
        "**Descripción**\n"
        "Tampoco tiene tests.\n\n"
        "**Estado:** Futuro\n",
        encoding="utf-8",
    )

    resultado = analizar(doc, TESTS_DIR)

    assert set(resultado.pendientes) == {"RF-998", "RNF-997"}
    assert not any(h.req_id in {"RF-998", "RNF-997"} for h in resultado.huerfanos)
