"""
Modelos Pydantic (schemas) de la API del normalizador C4.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

# =============================================================================
# Compliance (reutilizable — lo usa api/linting.py)
# =============================================================================


class ComplianceLevel(StrEnum):
    """Nivel de cumplimiento de la validación."""

    COMPLIANT = "compliant"
    WARNING = "warning"
    BLOCKED = "blocked"


class ColorViolation(BaseModel):
    """Un color fuera de la paleta permitida."""

    color_hex: str = Field(..., description="Color hex que viola la política (e.g. #FF0000).")
    attribute_name: str = Field(..., description="Atributo XML donde apareció (e.g. fillColor).")
    element_id: str | None = Field(None, description="id de la mxCell con la violación.")


class StencilViolation(BaseModel):
    """Un stencil no permitido."""

    stencil_id: str = Field(..., description="Stencil no permitido (e.g. leanix).")
    element_id: str | None = Field(None, description="id de la mxCell que lo usa.")


class ComplianceCheck(BaseModel):
    """Resultado de la validación de compliance."""

    level: ComplianceLevel = Field(..., description="Nivel global de cumplimiento.")
    xml_well_formed: bool = Field(default=True, description="Si el XML está bien formado.")
    stencils_detected: list[str] = Field(default_factory=list, description="Stencils detectados.")
    stencil_violations: list[StencilViolation] = Field(default_factory=list)
    color_violations: list[ColorViolation] = Field(default_factory=list)
    requires_archimate_license: bool = Field(default=False)
    archimate_license_valid: bool = Field(default=False)
    errors: list[str] = Field(default_factory=list)


# =============================================================================
# Request / Response de normalización
# =============================================================================


class TitleBlockInput(BaseModel):
    """Campos del cajetín ISO 7200 (todos opcionales)."""

    project: str | None = Field(None, description="Proyecto.")
    title: str | None = Field(None, description="Título. Si se omite, se usa el nombre del diagrama.")
    doc_type: str | None = Field(None, description="As-Is / To-Be / ...")
    drawn_by: str | None = Field(None, description="Dibujó.")
    approved_by: str | None = Field(None, description="Revisó / arquitecto.")
    date: str | None = Field(None, description="Fecha ISO. Por defecto: hoy.")
    revision: str | None = Field(None, description="Revisión. Por defecto: A.")


class NormalizeRequest(BaseModel):
    """Petición de normalización Draw.io crudo → C4."""

    xml_content: str = Field(
        ...,
        min_length=1,
        max_length=10_485_760,  # 10 MB
        description="XML Draw.io crudo (mxfile o mxGraphModel).",
    )
    c4_level: int = Field(default=2, ge=1, le=3, description="Nivel C4 objetivo (1, 2 o 3).")
    classifier: Literal["heuristic", "llm", "auto"] = Field(
        default="heuristic", description="Estrategia de clasificación a C4."
    )
    title_block: TitleBlockInput | None = Field(default=None, description="Datos del cajetín ISO 7200.")
    run_compliance_check: bool = Field(
        default=False, description="Si true, corre el linter de compliance sobre el XML C4 de salida."
    )


class NormalizeReportModel(BaseModel):
    """Resumen de lo que hizo el motor (espejo de c4norm.NormalizeReport)."""

    diagram_name: str = ""
    c4_level: int = 2
    node_count: int = 0
    edge_count: int = 0
    inferred_edges: int = 0
    grounded_nodes: int = 0
    type_histogram: dict[str, int] = Field(default_factory=dict)
    low_confidence: list[str] = Field(default_factory=list)
    scale: str = "1:1"
    overflow: bool = False
    sheet: str = "A3"
    orientation: str = "landscape"
    engine: str = ""
    sheets: int = 1
    cross_sheet_edges: int = 0


class NormalizeResponse(BaseModel):
    """Respuesta de normalización."""

    xml_c4: str = Field(..., description="XML Draw.io conforme a C4, listo para Confluence.")
    report: NormalizeReportModel = Field(..., description="Resumen del procesamiento.")
    compliance: ComplianceCheck | None = Field(None, description="Compliance (si se solicitó).")


# =============================================================================
# Misceláneos
# =============================================================================


class HealthResponse(BaseModel):
    """Respuesta del health check."""

    status: str = Field(default="healthy", description="Estado del servicio.")
    version: str = Field(default="0.1.0", description="Versión de la API.")
    layout_engine: str = Field(default="layered", description="Motor de layout disponible: 'elk' o 'layered'.")
    uptime_seconds: float | None = Field(None, description="Tiempo de vida del proceso en segundos.")


class ErrorResponse(BaseModel):
    """Respuesta de error estándar."""

    error: str = Field(..., description="Tipo/código de error.")
    message: str = Field(..., description="Mensaje legible.")
    detail: list[dict[str, Any]] | None = Field(None, description="Detalles adicionales.")
