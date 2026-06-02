"""
Fixtures de pytest para los tests del normalizador C4.

Sólo muestras de XML reutilizables (compliance/parsing). Los mocks de la antigua
plataforma de rendering (Redis, ARQ, S3/boto3) se retiraron junto con esa capa.
"""

from __future__ import annotations

import pytest

# =============================================================================
# Muestras de XML
# =============================================================================


@pytest.fixture
def valid_xml_basic() -> str:
    """XML Draw.io válido y básico, sin stencils."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<mxGraphModel dx="1422" dy="794" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="827" pageHeight="1169" math="0" shadow="0">
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
    <mxCell id="2" value="Hello World" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#4A90D9;strokeColor=#333333;fontColor=#1A1A1A;" vertex="1" parent="1">
      <mxGeometry x="360" y="200" width="120" height="60" as="geometry"/>
    </mxCell>
  </root>
</mxGraphModel>"""


@pytest.fixture
def valid_xml_with_aws() -> str:
    """XML Draw.io con shapes de stencil AWS."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<mxGraphModel>
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
    <mxCell id="2" value="EC2" style="shape=aws4.instance;fillColor=#4A90D9;strokeColor=#333333;" vertex="1" parent="1">
      <mxGeometry x="200" y="150" width="80" height="80" as="geometry"/>
    </mxCell>
  </root>
</mxGraphModel>"""


@pytest.fixture
def valid_xml_with_archimate() -> str:
    """XML Draw.io con shapes de stencil ArchiMate."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<mxGraphModel>
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
    <mxCell id="2" value="Application" style="shape=archimate3.application;fillColor=#4A90D9;strokeColor=#333333;" vertex="1" parent="1">
      <mxGeometry x="300" y="200" width="100" height="100" as="geometry"/>
    </mxCell>
  </root>
</mxGraphModel>"""


@pytest.fixture
def valid_xml_with_disallowed_color() -> str:
    """XML Draw.io con un color fuera de la paleta permitida."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<mxGraphModel>
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
    <mxCell id="2" value="Red Box" style="fillColor=#FF0000;strokeColor=#333333;" vertex="1" parent="1">
      <mxGeometry x="100" y="100" width="100" height="100" as="geometry"/>
    </mxCell>
  </root>
</mxGraphModel>"""


@pytest.fixture
def invalid_xml() -> str:
    """XML mal formado para probar manejo de errores."""
    return """<mxGraphModel>
  <root>
    <mxCell id="0">
    <mxCell id="1" parent="0">
  </root>
</mxGraphBROKEN>"""


@pytest.fixture
def empty_xml() -> str:
    """Contenido XML vacío."""
    return ""


# =============================================================================
# Settings de prueba (compliance)
# =============================================================================


@pytest.fixture
def test_settings_dict() -> dict:
    """Ajustes de compliance para sobrescribir config en tests."""
    return {
        "ALLOWED_STENCILS": "aws4,gcp2,azure,archimate3,c4,cisco,oci",
        "ALLOWED_COLORS": "4A90D9,333333,1A1A1A,50C878,FFFFFF",
        "ARCHIMATE_LICENSE_KEY": "",
    }
