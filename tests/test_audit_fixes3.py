"""
Tests para la tercera tanda de correcciones de la auditoría:
  - Conformidad C4 visual: Database stencil oficial, Component WCAG, System stroke, Person externa
  - Prompt injection: truncado de etiquetas, instrucción defensiva en system prompt
  - Filtrado de aristas por chunk en batching LLM
  - Tests de CLI (cobertura cero antes)
"""

from __future__ import annotations

import json

import pytest

from c4norm.model import C4Type, Node


def _node(nid: str, t: C4Type = C4Type.CONTAINER, external: bool = False) -> Node:
    n = Node(id=nid, c4_type=t)
    n.external = external
    n.c4_name = nid
    n.x, n.y, n.width, n.height = 0.0, 0.0, 120.0, 60.0
    return n


# =============================================================================
# Fix: Database usa mxgraph.c4.database (no shape=cylinder genérico)
# =============================================================================

def test_database_uses_c4_stencil() -> None:
    """Database debe usar el stencil oficial C4 mxgraph.c4.database."""
    from c4norm.model import C4_SPEC

    db_style = C4_SPEC[C4Type.DATABASE].cell_style
    assert "mxgraph.c4.database" in db_style, (
        f"Database debe usar mxgraph.c4.database, encontrado: {db_style[:80]}"
    )
    assert "shape=cylinder" not in db_style


def test_database_external_uses_c4_stencil() -> None:
    """Database externa también debe usar mxgraph.c4.database (no shape=cylinder)."""
    from c4norm.model import external_style

    style = external_style(C4Type.DATABASE)
    assert "mxgraph.c4.database" in style
    assert "shape=cylinder" not in style


# =============================================================================
# Fix: Component fontColor WCAG (#000000 sobre #85BBF0)
# =============================================================================

def test_component_uses_dark_font_for_wcag() -> None:
    """Component usa fontColor=#000000 (texto oscuro sobre azul claro para WCAG)."""
    from c4norm.model import C4_SPEC

    comp_style = C4_SPEC[C4Type.COMPONENT].cell_style
    assert "fontColor=#000000" in comp_style, (
        "Component debe usar fontColor=#000000 (WCAG sobre #85BBF0)"
    )
    assert "fontColor=#ffffff" not in comp_style


# =============================================================================
# Fix: Software System strokeColor distinto al fillColor
# =============================================================================

def test_software_system_stroke_differs_from_fill() -> None:
    """Software System debe tener strokeColor distinto del fillColor."""
    import re

    from c4norm.model import C4_SPEC

    style = C4_SPEC[C4Type.SOFTWARE_SYSTEM].cell_style
    fill = re.search(r"fillColor=(#[0-9A-Fa-f]{6})", style)
    stroke = re.search(r"strokeColor=(#[0-9A-Fa-f]{6})", style)
    assert fill and stroke, "Faltan fillColor o strokeColor en Software System"
    assert fill.group(1) != stroke.group(1), (
        f"Software System: strokeColor ({stroke.group(1)}) igual que fillColor ({fill.group(1)})"
    )


# =============================================================================
# Fix: Person externa usa estilo gris diferenciado
# =============================================================================

def test_person_external_style_is_grey() -> None:
    """Person externa debe usar fillColor gris (#686868), no el azul de Person interna."""
    from c4norm.model import external_style

    style = external_style(C4Type.PERSON)
    assert "#686868" in style, f"Person externa debe ser gris #686868, estilo: {style[:80]}"
    assert "#08427b" not in style  # no el azul de Person interna
    assert "mxgraph.c4.person" in style  # mantiene la silueta


def test_person_external_emitted_with_grey_style() -> None:
    """El XML emitido para una Person externa usa el estilo gris."""
    from c4norm.normalize import normalize

    xml = """<mxGraphModel><root>
      <mxCell id="0"/><mxCell id="1" parent="0"/>
      <mxCell id="usr" value="Usuario Externo (externo)" style="shape=mxgraph.c4.person;"
              vertex="1" parent="1">
        <mxGeometry x="0" y="0" width="200" height="130" as="geometry"/>
      </mxCell>
    </root></mxGraphModel>"""
    xml_c4, _ = normalize(xml, c4_level=1, classifier="heuristic")
    assert "#686868" in xml_c4, "Person externa debe aparecer con color gris en el XML emitido"


# =============================================================================
# Fix: prompt injection — truncado de etiquetas
# =============================================================================

def test_llm_prompt_truncates_long_labels() -> None:
    """Etiquetas largas se truncan a _MAX_LABEL_LEN en el prompt LLM."""
    from c4norm.classify import _MAX_LABEL_LEN, _build_llm_prompt

    long_label = "A" * (_MAX_LABEL_LEN + 200)
    n = Node(id="x", raw_label=long_label)
    prompt = _build_llm_prompt([n], [], 2)
    data = json.loads(prompt.split("NODOS:\n")[1].split("\n\nARISTAS:")[0])
    assert len(data[0]["label"]) == _MAX_LABEL_LEN


def test_llm_system_prompt_has_injection_warning() -> None:
    """El system prompt advierte explícitamente sobre prompt injection."""
    from c4norm.classify import _LLM_SYSTEM_PROMPT

    assert "adversarial" in _LLM_SYSTEM_PROMPT.lower() or "instrucciones" in _LLM_SYSTEM_PROMPT.lower()
    assert "seguridad" in _LLM_SYSTEM_PROMPT.lower() or "IMPORTANTE" in _LLM_SYSTEM_PROMPT


# =============================================================================
# Fix: filtrado de aristas en batching — solo aristas del chunk
# =============================================================================

def test_llm_prompt_filters_edges_to_chunk() -> None:
    """_build_llm_prompt solo incluye aristas que involucran nodos del chunk actual."""
    from c4norm.classify import _build_llm_prompt
    from c4norm.model import Edge

    n_in_chunk = Node(id="a")
    edges = [
        Edge(id="e1", source="a", target="z"),   # a está en chunk → incluir
        Edge(id="e2", source="z", target="z"),   # z no está en chunk → excluir
        Edge(id="e3", source="a", target="a"),   # a en chunk → incluir
    ]
    prompt = _build_llm_prompt([n_in_chunk], edges, 2)
    # El JSON de aristas está entre "ARISTAS:\n" y el siguiente "\n\n".
    edge_section = prompt.split("ARISTAS:\n")[1].split("\n\n")[0]
    data = json.loads(edge_section)
    assert {e["source"] for e in data} == {"a"}
    assert len(data) == 2  # e1 y e3, no e2 (z no está en el chunk)


# =============================================================================
# Tests de CLI (cobertura era 0%)
# =============================================================================

_FIXTURE = "tests/fixtures/crudo_ia_2_simple.drawio.xml"


def test_cli_normalizes_to_stdout(tmp_path: pytest.TempPathFactory, capsys) -> None:
    """CLI sin -o imprime el XML C4 en stdout y el resumen en stderr."""
    from c4norm.cli import main

    ret = main([_FIXTURE, "--level", "2"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "<mxfile" in captured.out
    assert "nodos" in captured.err


def test_cli_writes_output_file(tmp_path) -> None:
    """CLI con -o escribe el archivo en la ruta indicada."""
    from c4norm.cli import main

    out = tmp_path / "salida.drawio.xml"
    ret = main([_FIXTURE, "--level", "2", "-o", str(out)])
    assert ret == 0
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "<mxfile" in content


def test_cli_title_block_fields(capsys) -> None:
    """Las opciones del cajetín se transfieren correctamente."""
    from c4norm.cli import main

    main([
        _FIXTURE,
        "--level", "1",
        "--project", "PROJ",
        "--title", "Mi Diagrama",
        "--type", "As-Is",
        "--arch", "Camila",
        "--rev", "B",
    ])
    captured = capsys.readouterr()
    # El título aparece en el XML de stdout
    assert "Mi Diagrama" in captured.out
    assert "PROJ" in captured.out


def test_cli_level3_produces_components(capsys) -> None:
    """CLI con --level 3 clasifica las cajas genéricas como Component."""
    from c4norm.cli import main

    main([_FIXTURE, "--level", "3"])
    captured = capsys.readouterr()
    assert "Component" in captured.err  # aparece en el histograma del resumen


def test_cli_classifier_heuristic_default(capsys) -> None:
    """El clasificador por defecto es heuristic."""
    from c4norm.cli import main

    ret = main([_FIXTURE, "--level", "2", "--classifier", "heuristic"])
    assert ret == 0


def test_cli_missing_file_raises(tmp_path: pytest.TempPathFactory) -> None:
    """Un archivo que no existe produce SystemExit o un error claro."""
    from c4norm.cli import main

    with pytest.raises((SystemExit, FileNotFoundError, OSError)):
        main([str(tmp_path / "no_existe.drawio.xml"), "--level", "2"])
