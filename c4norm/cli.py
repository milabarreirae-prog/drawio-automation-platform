"""
CLI del spike: normaliza un .drawio crudo a C4 con hoja de ingeniería.

    python -m c4norm <input.drawio.xml> --level 2 --project "BFCL" \
        --title "Arquitectura As-Is RPTI" --type As-Is --arch "Camila" \
        --drawn-by "c4norm" --rev A --sheet A3 -o salida.drawio.xml
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

from c4norm.leanix import inventory_to_diagram, leanix_to_c4
from c4norm.normalize import NormalizeReport, normalize
from c4norm.obsidian import export_obsidian
from c4norm.sheet import TitleBlock


def _sink_basename(output: Path | None, default: str) -> str:
    """Nombre base del artefacto para el sink Obsidian (sin sufijo compuesto)."""
    if output is None:
        return default
    basename = output.name
    for suffix in (".drawio.xml", ".xml", ".drawio"):
        if basename.endswith(suffix):
            return basename[: -len(suffix)]
    return basename


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="c4norm", description="Normaliza Draw.io crudo a C4.")
    parser.add_argument("input", type=Path, nargs="?", default=None, help="Ruta al .drawio.xml de entrada")
    parser.add_argument(
        "--from-leanix", type=Path, default=None, metavar="response.json",
        help="Ruta a un JSON de respuesta GraphQL allFactSheets de LeanIX (camino tipado, no .drawio.xml)",
    )
    parser.add_argument("--level", type=int, default=2, choices=[1, 2, 3], help="Nivel C4 objetivo")
    parser.add_argument("--classifier", default="heuristic", choices=["heuristic", "llm", "auto"])
    parser.add_argument("-o", "--output", type=Path, default=None, help="Salida (por defecto: stdout)")
    # Cajetín ISO 7200.
    parser.add_argument("--project", default="—")
    parser.add_argument("--title", default=None)
    parser.add_argument("--type", dest="doc_type", default="", help="As-Is / To-Be / ...")
    parser.add_argument("--drawn-by", default="c4norm")
    parser.add_argument("--arch", dest="approved_by", default="—", help="Revisó / Arquitecto")
    parser.add_argument("--date", default=None, help="Por defecto: hoy (ISO)")
    parser.add_argument("--rev", default="A")
    parser.add_argument("--org", dest="organization", default="", help="Organización (ISO 7200)")
    parser.add_argument("--doc-no", dest="doc_number", default="", help="Número de plano (ISO 7200)")
    parser.add_argument(
        "--obsidian", type=Path, default=None,
        help="Directorio de vault Obsidian: además exporta .drawio + nota .md (contrato por validar)",
    )
    args = parser.parse_args(argv)

    date = args.date or datetime.date.today().isoformat()
    tb = TitleBlock(
        project=args.project,
        title=args.title or "",  # si None, normalize usa el nombre del diagrama
        doc_type=args.doc_type,
        drawn_by=args.drawn_by,
        approved_by=args.approved_by,
        date=date,
        revision=args.rev,
        organization=args.organization,
        doc_number=args.doc_number,
    )
    if not tb.title:
        tb = None  # deja que normalize tome el nombre del diagrama

    if args.from_leanix:
        response = json.loads(args.from_leanix.read_text(encoding="utf-8"))
        diagram_name = args.title or "Inventario LeanIX"
        diagram, warnings = inventory_to_diagram(response, name=diagram_name)
        xml_out, _warnings = leanix_to_c4(response, c4_level=args.level, name=diagram_name, title_block=tb)
        por_validar = sum(1 for n in diagram.nodes if n.cmdb_status == "por validar")
        print(
            f"[c4norm leanix] {len(diagram.nodes)} nodos, {len(diagram.edges)} aristas, "
            f"{por_validar} por validar",
            file=sys.stderr,
        )
        for w in warnings:
            print(f"[c4norm leanix]   ⚠ {w}", file=sys.stderr)

        if args.output:
            args.output.write_text(xml_out, encoding="utf-8")
            print(f"[c4norm] escrito en {args.output}", file=sys.stderr)
        else:
            print(xml_out)

        if args.obsidian:
            basename = _sink_basename(args.output, diagram_name)
            leanix_report = NormalizeReport(
                diagram_name=diagram_name,
                c4_level=args.level,
                node_count=len(diagram.nodes),
                edge_count=len(diagram.edges),
                low_confidence=[n.c4_name for n in diagram.nodes if n.cmdb_status == "por validar"],
                warnings=warnings,
            )
            drawio_path, md_path = export_obsidian(xml_out, leanix_report, tb, args.obsidian, basename)
            print(f"[c4norm] Obsidian: {md_path} + {drawio_path}", file=sys.stderr)
        return 0

    if args.input is None:
        print(
            "[c4norm] error: se requiere <input> (.drawio.xml) o --from-leanix <response.json>",
            file=sys.stderr,
        )
        return 2

    xml_in = args.input.read_text(encoding="utf-8")
    xml_out, report = normalize(xml_in, c4_level=args.level, classifier=args.classifier, title_block=tb)

    flag = " ⚠ overflow (requiere multi-hoja)" if report.overflow else ""
    grounded = f", {report.grounded_nodes} anclados" if report.grounded_nodes else ""
    print(
        f"[c4norm] {report.diagram_name}: {report.node_count} nodos, "
        f"{report.edge_count} aristas ({report.inferred_edges} inferidas){grounded}, "
        f"escala {report.scale}, hoja ≈{report.sheet} {report.orientation}, "
        f"motor {report.engine} → tipos {report.type_histogram}{flag}",
        file=sys.stderr,
    )

    if args.output:
        args.output.write_text(xml_out, encoding="utf-8")
        print(f"[c4norm] escrito en {args.output}", file=sys.stderr)
    else:
        print(xml_out)

    if args.obsidian:
        basename = _sink_basename(args.output, report.diagram_name)
        drawio_path, md_path = export_obsidian(xml_out, report, tb, args.obsidian, basename)
        print(f"[c4norm] Obsidian: {md_path} + {drawio_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
