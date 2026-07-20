"""
Sink de exportación a Obsidian (backlog B-05).

Genera, junto al `.drawio` normalizado, una nota Markdown con frontmatter
YAML que embebe el diagrama (`![[archivo.drawio]]`) para un vault de Obsidian.

El contrato real del vault (nombres de campos del frontmatter, taxonomía de
`tipo`, etc.) lo define la bibliotecaria de la célula
``knowledge-base-personal-obsidian`` y hoy se desconoce; por eso el frontmatter
aquí es una ASUNCIÓN y se marca explícitamente `contrato_vault: por_validar`
tanto en el frontmatter como en el cuerpo de la nota. El motor no inventa:
cualquier dato de baja confianza o advertencia del reporte se traslada tal
cual a la nota, nunca se oculta.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from c4norm.normalize import NormalizeReport
    from c4norm.sheet import TitleBlock


def _yaml_str(value: str) -> str:
    """Envuelve un escalar en comillas dobles YAML, escapando `\\` y `"`."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _slugify(basename: str) -> str:
    """Slug defensivo: minúsculas, espacios→'-', sólo [a-z0-9._-]."""
    slug = basename.strip().lower()
    # Cualquier separador de ruta se trata como espacio (evita escapar out_dir).
    slug = slug.replace("\\", " ").replace("/", " ")
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"[^a-z0-9._-]", "", slug)
    slug = slug.strip("-")
    return slug or "diagrama"


def render_obsidian_note(
    report: NormalizeReport,
    title_block: TitleBlock | None,
    drawio_filename: str,
) -> str:
    """Renderiza la nota Markdown (frontmatter YAML + cuerpo) para el vault.

    Ver el docstring del módulo: el contrato de frontmatter es provisional.
    """
    title = ""
    if title_block is not None:
        title = getattr(title_block, "title", "") or ""
    if not title:
        title = report.diagram_name

    doc_type = getattr(title_block, "doc_type", "") if title_block else ""
    project = (getattr(title_block, "project", "") if title_block else "") or "—"
    revision = (getattr(title_block, "revision", "") if title_block else "") or "A"
    date = (getattr(title_block, "date", "") if title_block else "") or ""

    frontmatter_lines = [
        "---",
        f"title: {_yaml_str(title)}",
        f"tipo: {_yaml_str(doc_type)}",
        f"proyecto: {_yaml_str(project)}",
        f"c4_level: {report.c4_level}",
        f"escala: {_yaml_str(report.scale)}",
        f"hoja: {_yaml_str(report.sheet)}",
        f"motor: {_yaml_str(report.engine)}",
        f"nodos: {report.node_count}",
        f"aristas: {report.edge_count}",
        f"revision: {_yaml_str(revision)}",
        f"fecha: {_yaml_str(date)}",
        "tags: [c4, diagrama, drawio]",
        "contrato_vault: por_validar",
        "---",
    ]

    body_lines = [
        f"# {title}",
        "",
        f"![[{drawio_filename}]]",
        "",
        "## Gobernanza",
        "",
    ]
    if report.low_confidence:
        body_lines.append("Nodos de baja confianza (por validar):")
        for node_name in report.low_confidence:
            body_lines.append(f"- {node_name}")
        body_lines.append("")
    if report.warnings:
        body_lines.append("Advertencias del motor:")
        for warning in report.warnings:
            body_lines.append(f"- {warning}")
        body_lines.append("")
    body_lines.append(
        "> Contrato de vault por validar con la bibliotecaria (knowledge-base-personal-obsidian)."
    )

    return "\n".join(frontmatter_lines) + "\n\n" + "\n".join(body_lines) + "\n"


def export_obsidian(
    xml_out: str,
    report: NormalizeReport,
    title_block: TitleBlock | None,
    out_dir: Path,
    basename: str,
) -> tuple[Path, Path]:
    """Escribe `<out_dir>/<basename>.drawio` + `.md` (nota Obsidian). Devuelve sus paths."""
    slug = _slugify(basename)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    drawio_path = out_dir / f"{slug}.drawio"
    md_path = out_dir / f"{slug}.md"

    drawio_path.write_text(xml_out, encoding="utf-8")
    note = render_obsidian_note(report, title_block, drawio_path.name)
    md_path.write_text(note, encoding="utf-8")

    return drawio_path, md_path
