"""Verificador de trazabilidad de requerimientos (RF/RNF) contra tests reales en disco.

Contrato
--------
Lee ``wiki/REQUERIMIENTOS_v1.md`` y extrae cada requerimiento (``RF-\\d+`` / ``RNF-\\d+``)
desde sus encabezados markdown (``## RF-001: ...``, ``### RNF-002: ...``, etc.). Para
cada requerimiento recolecta TODAS las referencias a tests que aparecen (a) en el cuerpo
de su propia sección (desde su encabezado hasta el siguiente encabezado de requerimiento
o el fin del documento) y (b) en su fila de la matriz de trazabilidad markdown, si existe.

Una referencia tiene la forma de un node-id de pytest: ``(tests/)?test_algo.py`` con cero
o más sufijos ``::simbolo`` (clase, método o función; se admite ``*`` como comodín y se
ignoran sufijos de parametrización ``[...]``).

Una referencia es VÁLIDA si:
  1. el archivo ``tests/<archivo>.py`` existe en disco, Y
  2. si la referencia trae un símbolo final concreto (no comodín), ese símbolo aparece
     como texto (substring) en el contenido del archivo.

Clasificación de cada requerimiento:
  - PENDIENTE_DECLARADO: su encabezado contiene el marcador "Futuro" o "EN DESARROLLO".
    Se reporta aparte; NUNCA cuenta como huérfano, tenga o no referencias.
  - HUÉRFANO: no está marcado como pendiente y no tiene NINGUNA referencia válida.
  - OK: tiene al menos una referencia válida.

Este módulo expone la función ``verificar()`` (usada por los tests) además de un CLI
(``python scripts/verificar_trazabilidad_requerimientos.py``) que imprime un resumen
legible y termina con ``sys.exit(1)`` si hay al menos un huérfano, o ``sys.exit(0)`` si no.

No depende de nada fuera de la librería estándar (re, sys, pathlib, dataclasses).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH_DEFAULT = REPO_ROOT / "wiki" / "REQUERIMIENTOS_v1.md"
TESTS_DIR_DEFAULT = REPO_ROOT / "tests"

_REQ_HEADER_RE = re.compile(r"^#{2,4}\s*((?:RF|RNF)-\d+)(.*)$", re.MULTILINE)
_MATRIX_ROW_RE = re.compile(r"^\|\s*\*\*((?:RF|RNF)-\d+)\*\*\s*\|(.*)$", re.MULTILINE)
_TEST_REF_RE = re.compile(r"(?:tests/)?test_\w+\.py(?:::[\w\[\]|*]+)*")
_PARAM_SUFFIX_RE = re.compile(r"\[.*\]$")
_PENDING_MARKERS = ("futuro", "en desarrollo")


@dataclass
class RefCheck:
    """Resultado de validar una referencia individual contra disco."""

    referencia: str
    valida: bool
    motivo: str


@dataclass
class Huerfano:
    """Un requerimiento sin ninguna referencia de test que resuelva a algo real."""

    req_id: str
    motivos: list[str] = field(default_factory=list)


@dataclass
class ResultadoTrazabilidad:
    """Clasificación completa de todos los requerimientos encontrados en el doc."""

    ok: list[str] = field(default_factory=list)
    huerfanos: list[Huerfano] = field(default_factory=list)
    pendientes: list[str] = field(default_factory=list)


def _es_pendiente_declarado(texto_encabezado: str) -> bool:
    """True si el texto del encabezado marca el requerimiento como Futuro/EN DESARROLLO."""
    texto_normalizado = texto_encabezado.lower()
    return any(marcador in texto_normalizado for marcador in _PENDING_MARKERS)


def _secciones_por_requerimiento(texto_doc: str) -> dict[str, str]:
    """Mapea cada req-id a (encabezado + cuerpo hasta el siguiente encabezado de requerimiento)."""
    encabezados = list(_REQ_HEADER_RE.finditer(texto_doc))
    secciones: dict[str, str] = {}
    for i, match in enumerate(encabezados):
        req_id = match.group(1)
        inicio = match.start()
        fin = encabezados[i + 1].start() if i + 1 < len(encabezados) else len(texto_doc)
        # Si el mismo ID aparece más de una vez (no debería), concatenamos las secciones.
        seccion = texto_doc[inicio:fin]
        secciones[req_id] = secciones.get(req_id, "") + seccion
    return secciones


def _encabezados_por_requerimiento(texto_doc: str) -> dict[str, str]:
    """Mapea cada req-id al texto completo de su(s) línea(s) de encabezado."""
    encabezados: dict[str, str] = {}
    for match in _REQ_HEADER_RE.finditer(texto_doc):
        req_id = match.group(1)
        encabezados[req_id] = encabezados.get(req_id, "") + " " + match.group(2)
    return encabezados


def _refs_de_matriz(texto_doc: str) -> dict[str, list[str]]:
    """Mapea cada req-id a las referencias de test encontradas en su fila de la matriz."""
    refs: dict[str, list[str]] = {}
    for match in _MATRIX_ROW_RE.finditer(texto_doc):
        req_id = match.group(1)
        fila = match.group(2)
        refs.setdefault(req_id, []).extend(m.group(0) for m in _TEST_REF_RE.finditer(fila))
    return refs


def _validar_referencia(referencia: str, raiz_tests: Path) -> RefCheck:
    """Valida una única referencia tipo pytest-node-id contra el árbol de tests en disco."""
    partes = referencia.split("::")
    archivo_token = partes[0]
    if archivo_token.startswith("tests/"):
        archivo_token = archivo_token[len("tests/") :]

    ruta_archivo = raiz_tests / archivo_token
    if not ruta_archivo.is_file():
        return RefCheck(referencia, False, f"archivo no existe: tests/{archivo_token}")

    simbolos = partes[1:]
    if not simbolos:
        return RefCheck(referencia, True, "ok (solo archivo)")

    ultimo_simbolo = simbolos[-1]
    if ultimo_simbolo == "*":
        return RefCheck(referencia, True, "ok (comodín)")

    nombre_simbolo = _PARAM_SUFFIX_RE.sub("", ultimo_simbolo)
    contenido = ruta_archivo.read_text(encoding="utf-8")
    if nombre_simbolo in contenido:
        return RefCheck(referencia, True, "ok")
    return RefCheck(referencia, False, f"símbolo '{nombre_simbolo}' no encontrado en tests/{archivo_token}")


def analizar(ruta_doc: Path, raiz_tests: Path) -> ResultadoTrazabilidad:
    """Analiza el documento de requerimientos y clasifica cada RF/RNF en OK/huérfano/pendiente."""
    texto_doc = ruta_doc.read_text(encoding="utf-8")

    secciones = _secciones_por_requerimiento(texto_doc)
    encabezados = _encabezados_por_requerimiento(texto_doc)
    refs_matriz = _refs_de_matriz(texto_doc)

    resultado = ResultadoTrazabilidad()

    for req_id, seccion in secciones.items():
        referencias = [m.group(0) for m in _TEST_REF_RE.finditer(seccion)]
        referencias.extend(refs_matriz.get(req_id, []))

        if _es_pendiente_declarado(encabezados.get(req_id, "")):
            resultado.pendientes.append(req_id)
            continue

        if not referencias:
            resultado.huerfanos.append(Huerfano(req_id, ["sin referencias a tests en la sección"]))
            continue

        checks = [_validar_referencia(ref, raiz_tests) for ref in referencias]
        if any(c.valida for c in checks):
            resultado.ok.append(req_id)
        else:
            motivos = [f"{c.referencia} -> {c.motivo}" for c in checks]
            resultado.huerfanos.append(Huerfano(req_id, motivos))

    resultado.ok.sort()
    resultado.pendientes.sort()
    resultado.huerfanos.sort(key=lambda h: h.req_id)
    return resultado


def verificar(ruta_doc: Path, raiz_tests: Path) -> list[Huerfano]:
    """Función delgada e importable: devuelve solo la lista de huérfanos.

    Es el punto de entrada pensado para tests que quieren invocar la lógica de
    clasificación directamente (sin subprocess) contra un doc temporal.
    """
    return analizar(ruta_doc, raiz_tests).huerfanos


def _imprimir_resumen(resultado: ResultadoTrazabilidad) -> None:
    total = len(resultado.ok) + len(resultado.huerfanos) + len(resultado.pendientes)
    print("=== Trazabilidad de requerimientos (RF/RNF) ===")
    print(f"Total requerimientos analizados: {total}")
    print(f"  OK (>=1 referencia válida):        {len(resultado.ok)}")
    print(f"  Pendientes declarados (Futuro/ED):  {len(resultado.pendientes)}")
    print(f"  HUÉRFANOS:                          {len(resultado.huerfanos)}")
    print()

    if resultado.pendientes:
        print("Pendientes declarados (no cuentan como huérfanos):")
        for req_id in resultado.pendientes:
            print(f"  - {req_id}")
        print()

    if resultado.huerfanos:
        print("Requerimientos HUÉRFANOS (sin evidencia real en disco):")
        for huerfano in resultado.huerfanos:
            print(f"  - {huerfano.req_id}:")
            for motivo in huerfano.motivos:
                print(f"      * {motivo}")
        print()
        print(f"RESULTADO: {len(resultado.huerfanos)} requerimiento(s) huérfano(s). Ver detalle arriba.")
    else:
        print("RESULTADO: cero huérfanos. Todos los RF/RNF no-pendientes tienen evidencia real en disco.")


def main() -> int:
    """CLI: analiza el doc real del repo e imprime el resumen. Retorna el exit code."""
    # Fuerza UTF-8 en stdout: en Windows la consola por defecto usa el codepage local,
    # lo que rompe el texto en español (tildes, íconos) al capturar la salida (p.ej. subprocess).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    resultado = analizar(DOC_PATH_DEFAULT, TESTS_DIR_DEFAULT)
    _imprimir_resumen(resultado)
    return 1 if resultado.huerfanos else 0


if __name__ == "__main__":
    sys.exit(main())
