"""
CLI del spike: normaliza un .drawio crudo a C4 con hoja de ingeniería.

    python -m c4norm <input.drawio.xml> --level 2 --project "BFCL" \
        --title "Arquitectura As-Is RPTI" --type As-Is --arch "Camila" \
        --drawn-by "c4norm" --rev A --sheet A3 -o salida.drawio.xml
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

from c4norm.normalize import normalize
from c4norm.obsidian import export_obsidian
from c4norm.sheet import TitleBlock


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="c4norm", description="Normaliza Draw.io crudo a C4.")
    parser.add_argument("input", type=Path, help="Ruta al .drawio.xml de entrada")
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

    xml_in = args.input.read_text(encoding="utf-8")
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
        if args.output:
            # Quita el sufijo compuesto .drawio.xml / .drawio / .xml para no producir
            # nombres como "salida.drawio.drawio" (Path.stem sólo pela el último sufijo).
            basename = args.output.name
            for suffix in (".drawio.xml", ".xml", ".drawio"):
                if basename.endswith(suffix):
                    basename = basename[: -len(suffix)]
                    break
        else:
            basename = report.diagram_name
        drawio_path, md_path = export_obsidian(xml_out, report, tb, args.obsidian, basename)
        print(f"[c4norm] Obsidian: {md_path} + {drawio_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
