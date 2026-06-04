"""
Tests para la tanda de higiene de la auditoría:
  - SecretStr para API keys (no se exponen en repr)
  - ISO 7200: organización + número de plano
  - DeploymentNode: descripción en el label
  - Advertencia al descartar páginas múltiples
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from c4norm.model import C4Type, Node
from c4norm.normalize import normalize
from c4norm.sheet import TitleBlock, render_frame_and_title_block

# =============================================================================
# SecretStr — las API keys no se exponen en repr()
# =============================================================================

def test_api_key_is_secret_str() -> None:
    """api_key y c4norm_llm_api_key son SecretStr y no aparecen en repr()."""
    from pydantic import SecretStr

    from api.config import Settings

    s = Settings(api_key="super-secreto", c4norm_llm_api_key="otra-clave")
    assert isinstance(s.api_key, SecretStr)
    assert isinstance(s.c4norm_llm_api_key, SecretStr)
    # El valor no debe aparecer en repr/str del objeto
    assert "super-secreto" not in repr(s)
    assert "otra-clave" not in repr(s)
    # Pero sí es accesible con get_secret_value()
    assert s.api_key.get_secret_value() == "super-secreto"


def test_auth_still_works_with_secret_str() -> None:
    """La autenticación funciona igual con SecretStr."""
    from api.config import Settings
    from api.main import _clear_rate_limit_state, app

    _clear_rate_limit_state()
    raw = "<mxGraphModel><root><mxCell id='0'/><mxCell id='1' parent='0'/></root></mxGraphModel>"
    with patch("api.main.settings", Settings(api_key="k3y")):
        client = TestClient(app)
        # Sin header → 401
        r401 = client.post("/api/v1/diagram/normalize", json={"xml_content": raw})
        # Header correcto → no 401/403 (será 200 o 422 según el XML, pero pasa auth)
        r_ok = client.post(
            "/api/v1/diagram/normalize",
            json={"xml_content": raw},
            headers={"Authorization": "Bearer k3y"},
        )
    assert r401.status_code == 401
    assert r_ok.status_code not in (401, 403)


def test_empty_api_key_means_no_auth() -> None:
    """Con api_key vacío (SecretStr('')) no se exige autenticación."""
    from api.config import Settings
    from api.main import _clear_rate_limit_state, app

    _clear_rate_limit_state()
    raw = "<mxGraphModel><root><mxCell id='0'/><mxCell id='1' parent='0'/></root></mxGraphModel>"
    with patch("api.main.settings", Settings(api_key="")):
        client = TestClient(app)
        r = client.post("/api/v1/diagram/normalize", json={"xml_content": raw})
    assert r.status_code not in (401, 403)


# =============================================================================
# ISO 7200 — organización + número de plano
# =============================================================================

def test_title_block_has_org_and_doc_number_fields() -> None:
    tb = TitleBlock(title="X", organization="ACME Corp", doc_number="PL-001")
    assert tb.organization == "ACME Corp"
    assert tb.doc_number == "PL-001"


def test_cajetin_renders_org_and_doc_number() -> None:
    tb = TitleBlock(title="Arq", project="P", organization="ACME Corp", doc_number="PL-001")
    cells = render_frame_and_title_block(1000, 1400, tb)
    blob = "\n".join(cells)
    assert "ACME Corp" in blob
    assert "PL-001" in blob
    assert "ORG:" in blob
    assert "plano" in blob


def test_cajetin_omits_org_doc_when_empty() -> None:
    """Sin org/doc_number, el cajetín no muestra esas etiquetas (compat hacia atrás)."""
    tb = TitleBlock(title="Arq", project="P")
    blob = "\n".join(render_frame_and_title_block(1000, 1400, tb))
    assert "ORG:" not in blob
    assert "N° plano" not in blob


def test_normalize_passes_org_doc_to_output() -> None:
    """El XML emitido incluye org y doc_number cuando se pasan en el TitleBlock."""
    raw = "<mxGraphModel><root><mxCell id='0'/><mxCell id='1' parent='0'/><mxCell id='a' value='A' vertex='1' parent='1'><mxGeometry x='0' y='0' width='100' height='60' as='geometry'/></mxCell></root></mxGraphModel>"
    tb = TitleBlock(title="T", organization="Banco XYZ", doc_number="ARQ-42")
    xml_c4, _ = normalize(raw, c4_level=2, title_block=tb)
    assert "Banco XYZ" in xml_c4
    assert "ARQ-42" in xml_c4


# =============================================================================
# DeploymentNode — descripción en el label
# =============================================================================

def test_deployment_node_label_includes_description() -> None:
    from c4norm.emit import _node_label

    n = Node(id="s", c4_type=C4Type.DEPLOYMENT_NODE)
    n.c4_description = "región us-east-1"
    label = _node_label(n)
    assert "%c4Description%" in label


def test_deployment_node_label_omits_empty_description() -> None:
    from c4norm.emit import _node_label

    n = Node(id="s", c4_type=C4Type.DEPLOYMENT_NODE)
    n.c4_description = ""
    label = _node_label(n)
    assert "%c4Description%" not in label


# =============================================================================
# Advertencia multi-página
# =============================================================================

_MULTI_PAGE = """<mxfile>
  <diagram id="d1" name="Página 1">
    <mxGraphModel><root>
      <mxCell id="0"/><mxCell id="1" parent="0"/>
      <mxCell id="a" value="A" vertex="1" parent="1"><mxGeometry x="0" y="0" width="100" height="60" as="geometry"/></mxCell>
    </root></mxGraphModel>
  </diagram>
  <diagram id="d2" name="Página 2">
    <mxGraphModel><root>
      <mxCell id="0"/><mxCell id="1" parent="0"/>
      <mxCell id="b" value="B" vertex="1" parent="1"><mxGeometry x="0" y="0" width="100" height="60" as="geometry"/></mxCell>
    </root></mxGraphModel>
  </diagram>
</mxfile>"""


def test_multipage_input_warns() -> None:
    _, report = normalize(_MULTI_PAGE, c4_level=2)
    assert report.input_page_count == 2
    assert report.warnings
    assert "páginas" in report.warnings[0]


def test_singlepage_input_no_warning() -> None:
    raw = "<mxGraphModel><root><mxCell id='0'/><mxCell id='1' parent='0'/><mxCell id='a' value='A' vertex='1' parent='1'><mxGeometry x='0' y='0' width='100' height='60' as='geometry'/></mxCell></root></mxGraphModel>"
    _, report = normalize(raw, c4_level=2)
    assert report.input_page_count == 1
    assert report.warnings == []


def test_api_response_includes_warnings_field() -> None:
    """El reporte de la API expone input_page_count y warnings."""
    from api.config import Settings
    from api.main import _clear_rate_limit_state, app

    _clear_rate_limit_state()
    with patch("api.main.settings", Settings(api_key="")):
        client = TestClient(app)
        r = client.post("/api/v1/diagram/normalize", json={"xml_content": _MULTI_PAGE})
    assert r.status_code == 200
    rep = r.json()["report"]
    assert rep["input_page_count"] == 2
    assert len(rep["warnings"]) >= 1
