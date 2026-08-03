"""
Demo V1 end-to-end — recorrido EN FRÍO con AMBAS fuentes (`viajes/V1/spec.md`).

Cierra el viaje V1 como evidencia-DoD: un recorrido de frío en el que CADA
fuente de entrada del producto atraviesa el CLI real (`python -m c4norm`) hasta
una nota Obsidian, sin red, sin credenciales y sin nada mockeado:

  * fuente cruda (`.drawio.xml` → `normalize`) → XML C4 + cajetín ISO 7200
    + nota Obsidian (`.md` + `.drawio` embebido);
  * fuente LeanIX (`--from-leanix <response.json>` → `inventory_to_diagram`
    + `leanix_to_c4`) → XML C4 + cajetín ISO 7200 + nota Obsidian.

Antes de la habilitación de `--obsidian` en el camino `--from-leanix`, esa
bandera se IGNORABA en silencio y el vault nunca se creaba: un vault vacío
en esta prueba sería la señal de que la capacidad nueva no está activa.

Cada prueba es un cold-run genuino: se lanza `python -m c4norm` como
subproceso (nada del motor se importa en el proceso del test) y se MIDE el
artefacto resultante en disco: `XMLLinter` para el gate de compliance,
`yaml.safe_load` para el frontmatter, una regex propia para el embed
`![[...]]` (sin reutilizar ningún path devuelto por el sink), y comparación
de bytes del `.drawio` embebido. Además fija el invariante Ax-C4N-001 (el
motor nunca inventa): el FactSheet ``techstack-legado`` (tipo
``TechnologyStack`` sin mapeo C4) se conserva en la nota y se marca
"por validar", nunca se descarta ni se le inventa un tipo.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

from api.config import get_settings
from api.linting import XMLLinter
from api.schemas import ComplianceLevel

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_CRUDO = FIXTURES / "crudo_ia_2_simple.drawio.xml"
FIXTURE_LEANIX = FIXTURES / "leanix_falabella.json"


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Corre `python -m c4norm <args>` como subproceso fresco (nada mockeado)."""
    return subprocess.run(
        [sys.executable, "-m", "c4norm", *args],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )


def _assert_compliance(xml_text: str) -> None:
    """Gate de compliance sobre el XML emitido (DoD): nunca BLOCKED y sin
    violaciones probadas de stencil/color; un WARNING sólo puede venir de
    contenido "por validar", nunca de un fallo de tipado/estilo.
    """
    result = XMLLinter(get_settings()).full_validation(xml_text)
    assert result.xml_well_formed is True
    assert result.level != ComplianceLevel.BLOCKED
    assert not result.stencil_violations
    assert not result.color_violations


def _assert_iso7200(xml_text: str) -> None:
    """Evidencia de cajetín ISO 7200: título, proyecto y arquitecta en el XML."""
    assert "c4norm-tb-title" in xml_text
    assert "BFCL" in xml_text
    assert "Camila" in xml_text


def _assert_nota_obsidian(vault: Path, expected_level: int) -> str:
    """Valida la nota Obsidian del vault: exactamente un `.md` + un `.drawio`,
    frontmatter YAML parseable con el nivel C4 esperado, y embed `![[...]]`
    resoluble en disco con fidelidad de bytes respecto al `.drawio` emitido.
    """
    md_files = list(vault.glob("*.md"))
    drawio_files = list(vault.glob("*.drawio"))
    assert len(md_files) == 1
    assert len(drawio_files) == 1

    md_text = md_files[0].read_text(encoding="utf-8")

    parts = md_text.split("---")
    assert parts[0] == ""
    frontmatter = yaml.safe_load(parts[1])
    assert isinstance(frontmatter, dict)
    assert frontmatter["c4_level"] == expected_level
    assert isinstance(frontmatter["title"], str)
    assert frontmatter["title"] != ""

    match = re.search(r"!\[\[(.+?)\]\]", md_text)
    assert match is not None, "no se encontró un embed ![[...]] en la nota"
    embed_target = match.group(1)

    embedded_path = vault / embed_target
    assert embedded_path.exists()
    assert embedded_path.is_file()
    assert embedded_path.read_text(encoding="utf-8") == drawio_files[0].read_text(
        encoding="utf-8"
    )
    assert len(embedded_path.read_text(encoding="utf-8")) > 0

    return md_text


# =============================================================================
# Fuente cruda (drawio) → C4 + ISO 7200 + Obsidian
# =============================================================================


def test_fuente_drawio_cruda_a_obsidian_c4_iso7200(tmp_path: Path) -> None:
    out_xml = tmp_path / "demo_v1_drawio.drawio.xml"
    vault = tmp_path / "vault_drawio"

    result = _run_cli(
        [
            str(FIXTURE_CRUDO),
            "--level",
            "2",
            "--title",
            "Demo V1 Drawio",
            "--project",
            "BFCL",
            "--arch",
            "Camila",
            "--rev",
            "A",
            "-o",
            str(out_xml),
            "--obsidian",
            str(vault),
        ]
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    xml_text = out_xml.read_text(encoding="utf-8")
    _assert_compliance(xml_text)
    _assert_iso7200(xml_text)

    _assert_nota_obsidian(vault, expected_level=2)


# =============================================================================
# Fuente LeanIX → C4 + ISO 7200 + Obsidian (la capacidad nueva de la bandera
# `--obsidian` en el camino `--from-leanix`)
# =============================================================================


def test_fuente_leanix_a_obsidian_c4_iso7200(tmp_path: Path) -> None:
    out_xml = tmp_path / "demo_v1_leanix.drawio.xml"
    vault = tmp_path / "vault_leanix"

    result = _run_cli(
        [
            "--from-leanix",
            str(FIXTURE_LEANIX),
            "--level",
            "1",
            "--title",
            "Demo V1 LeanIX",
            "--project",
            "BFCL",
            "--arch",
            "Camila",
            "--rev",
            "A",
            "-o",
            str(out_xml),
            "--obsidian",
            str(vault),
        ]
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    xml_text = out_xml.read_text(encoding="utf-8")
    _assert_compliance(xml_text)
    _assert_iso7200(xml_text)

    _assert_nota_obsidian(vault, expected_level=1)


# =============================================================================
# Ax-C4N-001 — el motor nunca inventa, también en la nota Obsidian
# =============================================================================


def test_leanix_no_inventa_por_validar_en_nota(tmp_path: Path) -> None:
    out_xml = tmp_path / "demo_v1_leanix.drawio.xml"
    vault = tmp_path / "vault_leanix"

    result = _run_cli(
        [
            "--from-leanix",
            str(FIXTURE_LEANIX),
            "--level",
            "1",
            "--title",
            "Demo V1 LeanIX",
            "--project",
            "BFCL",
            "--arch",
            "Camila",
            "--rev",
            "A",
            "-o",
            str(out_xml),
            "--obsidian",
            str(vault),
        ]
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    md_text = _assert_nota_obsidian(vault, expected_level=1)

    # El FactSheet techstack-legado (tipo TechnologyStack sin mapeo C4) se
    # CONSERVA y queda marcado "por validar" en el cuerpo de la nota — nunca
    # descartado ni tipado en silencio.
    assert "Stack Legado XYZ" in md_text
    assert "por validar" in md_text

    # La nota no es un stub: el frontmatter trae un título no vacío.
    frontmatter = yaml.safe_load(md_text.split("---")[1])
    assert isinstance(frontmatter["title"], str)
    assert frontmatter["title"] != ""
