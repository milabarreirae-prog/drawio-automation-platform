"""
Recorrido EN FRÍO del sink de exportación a Obsidian (B-05, `viajes/V1/spec.md`).

DoD de B-05 (tabla de rebanadas del spec): "DADO un diagrama C4 ya emitido por
`c4norm.emit`, CUANDO se invoca el exportador de sink, ENTONCES se genera un
`.md` con frontmatter válido (YAML parseable) y un embed `![[archivo.drawio]]`
cuyo path referenciado existe en disco en la misma corrida — verificado
abriendo el `.md` generado y resolviendo el path, no solo comprobando que la
función no lanzó excepción."

A diferencia de `tests/test_obsidian.py` (que llama `render_obsidian_note` /
`export_obsidian` in-process y hace substring-check), este archivo maneja el
CLI real (`python -m c4norm`) de punta a punta como subproceso — nada del
motor se mockea — y MIDE el artefacto resultante: parsea el YAML del
frontmatter con `pyyaml`, resuelve el embed con una regex independiente del
código bajo prueba, y compara bytes del `.drawio` embebido. También cubre el
camino rojo (gemelo_de_error): una entrada rota no debe degradar a una nota
vacía silenciosa.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_CRUDO = FIXTURES / "crudo_ia_2_simple.drawio.xml"


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Corre `python -m c4norm <args>` como subproceso fresco (nada mockeado)."""
    return subprocess.run(
        [sys.executable, "-m", "c4norm", *args],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )


class TestObsidianSinkCaminoVerde:
    """DADO un diagrama C4 ya emitido, CUANDO se invoca el sink, ENTONCES el
    `.md` producido trae frontmatter YAML válido y un embed resoluble en disco.
    """

    def test_frontmatter_es_yaml_valido_parseado(self, tmp_path: Path) -> None:
        out_xml = tmp_path / "out.drawio.xml"
        vault_dir = tmp_path / "vault"

        result = _run_cli(
            [
                str(FIXTURE_CRUDO),
                "--level",
                "2",
                "-o",
                str(out_xml),
                "--obsidian",
                str(vault_dir),
            ]
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"

        md_files = list(vault_dir.glob("*.md"))
        assert len(md_files) == 1
        md_text = md_files[0].read_text(encoding="utf-8")

        # Separa el frontmatter entre los dos primeros delimitadores "---" y
        # lo parsea de verdad con PyYAML: no basta con que la substring
        # "contrato_vault: por_validar" aparezca en el texto, tiene que ser
        # YAML válido.
        parts = md_text.split("---")
        assert parts[0] == ""
        frontmatter_raw = parts[1]
        frontmatter = yaml.safe_load(frontmatter_raw)

        assert isinstance(frontmatter, dict)
        assert isinstance(frontmatter["c4_level"], int)
        assert frontmatter["contrato_vault"] == "por_validar"
        assert isinstance(frontmatter["title"], str)
        assert frontmatter["title"] != ""

    def test_embed_resuelve_en_disco_con_contenido_fiel(self, tmp_path: Path) -> None:
        out_xml = tmp_path / "out.drawio.xml"
        vault_dir = tmp_path / "vault"

        result = _run_cli(
            [
                str(FIXTURE_CRUDO),
                "--level",
                "2",
                "-o",
                str(out_xml),
                "--obsidian",
                str(vault_dir),
            ]
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

        md_files = list(vault_dir.glob("*.md"))
        assert len(md_files) == 1
        md_text = md_files[0].read_text(encoding="utf-8")

        # Extrae el target del embed con una regex propia del test, sin
        # reutilizar ningún path que el sink haya devuelto en Python: el
        # embed viene sólo del TEXTO de la nota, como lo vería Obsidian.
        match = re.search(r"!\[\[(.+?)\]\]", md_text)
        assert match is not None, "no se encontró un embed ![[...]] en la nota"
        embed_target = match.group(1)

        embedded_path = vault_dir / embed_target
        assert embedded_path.exists()
        assert embedded_path.is_file()

        # Fidelidad: el embed apunta al artefacto .drawio real emitido en
        # esta misma corrida, no a uno vacío o desactualizado.
        drawio_files = list(vault_dir.glob("*.drawio"))
        assert len(drawio_files) == 1
        assert embedded_path.read_text(encoding="utf-8") == drawio_files[0].read_text(
            encoding="utf-8"
        )
        # El fixture de entrada tiene 6 nodos tipados/anclados; el .drawio
        # emitido no puede estar vacío.
        assert len(embedded_path.read_text(encoding="utf-8")) > 0

    def test_nada_inventado_marca_por_validar_en_cuerpo_y_frontmatter(
        self, tmp_path: Path
    ) -> None:
        out_xml = tmp_path / "out.drawio.xml"
        vault_dir = tmp_path / "vault"

        result = _run_cli(
            [
                str(FIXTURE_CRUDO),
                "--level",
                "2",
                "-o",
                str(out_xml),
                "--obsidian",
                str(vault_dir),
            ]
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

        md_files = list(vault_dir.glob("*.md"))
        assert len(md_files) == 1
        md_text = md_files[0].read_text(encoding="utf-8")

        frontmatter = yaml.safe_load(md_text.split("---")[1])
        assert frontmatter["contrato_vault"] == "por_validar"
        assert "Contrato de vault por validar" in md_text


class TestObsidianSinkCaminoRojo:
    """Gemelo_de_error: una entrada rota no debe degradar a un artefacto
    vacío indistinguible de una corrida legítima sin contenido.
    """

    def test_drawio_truncado_no_produce_md_y_falla_con_stderr(
        self, tmp_path: Path
    ) -> None:
        broken_input = tmp_path / "roto.drawio.xml"
        broken_input.write_text("<mxfile><diagram>", encoding="utf-8")

        out_xml = tmp_path / "out_roto.drawio.xml"
        vault_dir = tmp_path / "vault_roto"

        result = _run_cli(
            [
                str(broken_input),
                "--level",
                "2",
                "-o",
                str(out_xml),
                "--obsidian",
                str(vault_dir),
            ]
        )

        assert result.returncode != 0
        assert result.stderr.strip() != ""

        # La aserción que de verdad muerde: si el sink degradara a una nota
        # vacía en el camino de error, este glob dejaría de estar vacío.
        md_files = list(vault_dir.glob("*.md")) if vault_dir.exists() else []
        assert md_files == []

    def test_drawio_vacio_no_produce_md_y_falla(self, tmp_path: Path) -> None:
        broken_input = tmp_path / "vacio.drawio.xml"
        broken_input.write_text("", encoding="utf-8")

        out_xml = tmp_path / "out_vacio.drawio.xml"
        vault_dir = tmp_path / "vault_vacio"

        result = _run_cli(
            [
                str(broken_input),
                "--level",
                "2",
                "-o",
                str(out_xml),
                "--obsidian",
                str(vault_dir),
            ]
        )

        assert result.returncode != 0
        assert result.stderr.strip() != ""

        md_files = list(vault_dir.glob("*.md")) if vault_dir.exists() else []
        assert md_files == []
