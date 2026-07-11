"""
Tests de la pasada de enriquecimiento (Enricher) y su integración en normalize():
potenciar descripciones/relaciones, estandarizar, fusionar duplicados, integrar
título→cajetín y leyenda→clave C4 estándar. Con `chat` inyectado (sin red).
"""

from __future__ import annotations

import json

from c4norm.enrich import Enricher
from c4norm.legend import build_standard_legend
from c4norm.model import Annotation, C4Type, Diagram, Edge, Node
from c4norm.normalize import normalize


def _sample() -> Diagram:
    return Diagram(
        name="t",
        nodes=[
            Node(id="zone", c4_type=C4Type.DEPLOYMENT_NODE, c4_name="Zona"),
            Node(id="api", parent="zone", c4_type=C4Type.COMPONENT, c4_name="API"),
            Node(id="api_dup", parent="zone", c4_type=C4Type.COMPONENT, c4_name="API (copia)"),
            Node(id="db", parent="zone", c4_type=C4Type.DATABASE, c4_name="BD"),
        ],
        edges=[
            Edge(id="e1", source="api", target="db", c4_description="usa"),
            Edge(id="e2", source="api_dup", target="db", c4_description="usa"),
        ],
        annotations=[Annotation(id="note1", value="Nota larga y enredada", kind="note")],
    )


def _chat(payload: dict):
    return lambda _prompt: json.dumps(payload, ensure_ascii=False)


# =============================================================================
# Enricher (unidad)
# =============================================================================

def test_enriches_existing_nodes() -> None:
    d = _sample()
    res = Enricher(chat=_chat({
        "nodes": {"api": {"c4Description": "Orquesta pagos (por validar)", "c4Technology": "FastAPI"}},
    })).enrich(d, 3)
    api = d.node_by_id("api")
    assert api.c4_description == "Orquesta pagos (por validar)"
    assert api.c4_technology == "FastAPI"
    assert res.enriched_nodes == 1


def test_merges_duplicates_and_repoints_edges() -> None:
    d = _sample()
    res = Enricher(chat=_chat({"merges": [["api", "api_dup"]]})).enrich(d, 3)
    assert res.merged == 1
    assert d.node_by_id("api_dup") is None          # duplicado eliminado
    assert d.node_by_id("api") is not None           # superviviente
    # ambas aristas iban a db; tras re-apuntar y deduplicar, queda una.
    assert sum(1 for e in d.edges if e.target == "db") == 1


def test_never_merges_boundaries() -> None:
    d = _sample()
    # intento de fusionar la zona (boundary con hijos) con un componente
    res = Enricher(chat=_chat({"merges": [["zone", "api"]]})).enrich(d, 3)
    assert res.merged == 0
    assert d.node_by_id("zone") is not None
    assert d.node_by_id("api") is not None


def test_enriches_edges_and_notes_and_title() -> None:
    d = _sample()
    res = Enricher(chat=_chat({
        "title": "Plataforma de Pagos",
        "edges": [{"source": "api", "target": "db", "c4Description": "lee/escribe", "c4Technology": "JDBC"}],
        "notes": [{"id": "note1", "text": "Nota concisa"}],
        "changelog": ["Mejorada relación api→db"],
    })).enrich(d, 3)
    e = next(e for e in d.edges if e.source == "api" and e.target == "db")
    assert e.c4_description == "lee/escribe"
    assert e.c4_technology == "JDBC"
    assert d.annotations[0].value == "Nota concisa"
    assert res.title == "Plataforma de Pagos"
    assert res.changelog


def test_invalid_json_retries_then_raises() -> None:
    calls = {"n": 0}

    def flaky(_prompt: str) -> str:
        calls["n"] += 1
        return "no es json"

    import pytest
    with pytest.raises(ValueError, match="respuesta inválida"):
        Enricher(chat=flaky, retries=1).enrich(_sample(), 3)
    assert calls["n"] == 2


def test_requires_key_without_chat(monkeypatch) -> None:
    monkeypatch.delenv("C4NORM_LLM_API_KEY", raising=False)
    import pytest
    with pytest.raises(ValueError, match="C4NORM_LLM_API_KEY"):
        Enricher().enrich(_sample(), 3)


# =============================================================================
# Leyenda estándar
# =============================================================================

def test_standard_legend_covers_present_types() -> None:
    d = _sample()
    cells = build_standard_legend(d, 0.0, 0.0)
    ids = {c.id for c in cells}
    assert "legend-title" in ids
    assert "legend-component" in ids       # hay Component
    assert "legend-database" in ids        # hay Database
    assert "legend-deploymentnode" in ids  # hay DeploymentNode
    assert "legend-relationship" in ids    # hay aristas
    assert "legend-governance" not in ids  # ningún nodo trae confianza/CMDB
    assert all(c.kind == "legend" for c in cells)


def test_standard_legend_adds_governance_row_only_when_declared() -> None:
    d = _sample()
    d.node_by_id("api").confidence = "Baja"
    cells = build_standard_legend(d, 0.0, 0.0)
    gov = next(c for c in cells if c.id == "legend-governance")
    assert gov.kind == "legend"
    assert "Confianza" in gov.value and "CMDB" in gov.value


# =============================================================================
# Integración en normalize()
# =============================================================================

_XML = """<mxGraphModel><root>
  <mxCell id="0"/><mxCell id="1" parent="0"/>
  <mxCell id="t" value="Mi Diagrama" style="text;html=1;strokeColor=none;" vertex="1" parent="1">
    <mxGeometry x="40" y="0" width="200" height="30" as="geometry"/>
  </mxCell>
  <mxCell id="svc" value="Servicio" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">
    <mxGeometry x="40" y="60" width="160" height="60" as="geometry"/>
  </mxCell>
  <mxCell id="db" value="Base" style="shape=datastore;whiteSpace=wrap;html=1;" vertex="1" parent="1">
    <mxGeometry x="40" y="160" width="120" height="80" as="geometry"/>
  </mxCell>
  <mxCell id="leg" value="Leyenda" style="swimlane;horizontal=0;" vertex="1" parent="1">
    <mxGeometry x="300" y="200" width="200" height="80" as="geometry"/>
  </mxCell>
  <mxCell id="legitem" value="azul = negocio" style="rounded=1;html=1;" vertex="1" parent="leg">
    <mxGeometry x="20" y="40" width="120" height="30" as="geometry"/>
  </mxCell>
</root></mxGraphModel>"""


def test_normalize_enrich_integrates_title_and_legend() -> None:
    fake = Enricher(chat=_chat({
        "title": "Mi Diagrama",
        "title_id": "t",
        "nodes": {"svc": {"c4Description": "Hace cosas (por validar)"}},
        "changelog": ["Descripción de svc enriquecida"],
    }))
    xml_c4, rep = normalize(_XML, c4_level=3, enrich=True, enricher=fake)
    assert rep.enriched is True
    assert rep.changelog
    # leyenda estándar instalada; la original (azul=negocio) descartada
    assert "anno-legend-title" in xml_c4
    assert "azul = negocio" not in xml_c4
    # el título (id de origen "t") dejó de flotar como nota: va al cajetín
    assert 'id="anno-t"' not in xml_c4


def test_normalize_enrich_without_key_warns(monkeypatch) -> None:
    monkeypatch.delenv("C4NORM_LLM_API_KEY", raising=False)
    xml_c4, rep = normalize(_XML, c4_level=3, enrich=True)  # sin enricher ni clave
    assert rep.enriched is False
    assert any("Enriquecimiento omitido" in w for w in rep.warnings)
