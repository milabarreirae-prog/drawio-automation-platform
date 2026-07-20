"""
Tests del sink de exportación a Obsidian (backlog B-05).

Cubre la nota Markdown (frontmatter + gobernanza) y la escritura de archivos
(`.drawio` + `.md`), incluyendo el caso end-to-end sobre un fixture real.
"""

from __future__ import annotations

from pathlib import Path

from c4norm.normalize import NormalizeReport, normalize
from c4norm.obsidian import export_obsidian, render_obsidian_note
from c4norm.sheet import TitleBlock

FIXTURES = Path(__file__).parent / "fixtures"
IA2 = (FIXTURES / "crudo_ia_2_simple.drawio.xml").read_text(encoding="utf-8")


def _base_report(**overrides) -> NormalizeReport:
    defaults = {
        "diagram_name": "Diagrama de prueba",
        "c4_level": 2,
        "node_count": 6,
        "edge_count": 5,
        "scale": "1:1",
        "sheet": "A3",
        "engine": "layered",
    }
    defaults.update(overrides)
    return NormalizeReport(**defaults)


class TestRenderObsidianNote:
    def test_contains_embed_line(self) -> None:
        note = render_obsidian_note(_base_report(), None, "foo.drawio")
        assert "![[foo.drawio]]" in note.splitlines()

    def test_frontmatter_is_parseable(self) -> None:
        note = render_obsidian_note(_base_report(), None, "foo.drawio")
        parts = note.split("---")
        # parts[0] es "" (antes del primer delimitador), parts[1] el frontmatter.
        assert parts[0] == ""
        frontmatter = parts[1]
        assert 'title:' in frontmatter
        assert 'contrato_vault: por_validar' in frontmatter
        assert 'c4_level:' in frontmatter

    def test_title_with_quote_is_escaped(self) -> None:
        tb = TitleBlock(title='Sistema "Fénix"')
        note = render_obsidian_note(_base_report(), tb, "foo.drawio")
        frontmatter = note.split("---")[1]
        title_lines = [line for line in frontmatter.splitlines() if line.startswith("title:")]
        assert len(title_lines) == 1
        title_line = title_lines[0]
        assert title_line == 'title: "Sistema \\"Fénix\\""'

    def test_low_confidence_nodes_mentioned_in_governance(self) -> None:
        report = _base_report(low_confidence=["Nodo X"])
        note = render_obsidian_note(report, None, "foo.drawio")
        assert "## Gobernanza" in note
        governance = note.split("## Gobernanza", 1)[1]
        assert "Nodo X" in governance

    def test_no_low_confidence_or_warnings_still_has_contract_line(self) -> None:
        note = render_obsidian_note(_base_report(), None, "foo.drawio")
        assert "Contrato de vault por validar" in note

    def test_warnings_mentioned_in_governance(self) -> None:
        report = _base_report(warnings=["Cuidado con esto"])
        note = render_obsidian_note(report, None, "foo.drawio")
        governance = note.split("## Gobernanza", 1)[1]
        assert "Cuidado con esto" in governance

    def test_title_falls_back_to_diagram_name(self) -> None:
        report = _base_report(diagram_name="Nombre del diagrama")
        note = render_obsidian_note(report, None, "foo.drawio")
        assert "# Nombre del diagrama" in note


class TestExportObsidian:
    def test_writes_two_files_with_exact_xml(self, tmp_path: Path) -> None:
        xml_out = "<mxGraphModel><root/></mxGraphModel>"
        report = _base_report()
        drawio_path, md_path = export_obsidian(xml_out, report, None, tmp_path, "mi-diagrama")

        assert drawio_path.exists()
        assert md_path.exists()
        assert drawio_path.read_text(encoding="utf-8") == xml_out
        assert f"![[{drawio_path.name}]]" in md_path.read_text(encoding="utf-8")

    def test_basename_slugification(self, tmp_path: Path) -> None:
        report = _base_report()
        drawio_path, md_path = export_obsidian("<x/>", report, None, tmp_path, "My Diagram!")

        assert drawio_path.name == "my-diagram.drawio"
        assert md_path.name == "my-diagram.md"

    def test_creates_missing_out_dir(self, tmp_path: Path) -> None:
        out_dir = tmp_path / "nested" / "vault"
        report = _base_report()
        drawio_path, md_path = export_obsidian("<x/>", report, None, out_dir, "diagrama")

        assert drawio_path.parent == out_dir
        assert md_path.parent == out_dir


class TestExportObsidianEndToEnd:
    def test_normalize_then_export(self, tmp_path: Path) -> None:
        xml_out, report = normalize(IA2, c4_level=2)
        drawio_path, md_path = export_obsidian(xml_out, report, None, tmp_path, "ia2-demo")

        assert drawio_path.exists()
        assert md_path.exists()
        assert drawio_path.read_text(encoding="utf-8") == xml_out
        md_content = md_path.read_text(encoding="utf-8")
        assert f"![[{drawio_path.name}]]" in md_content
