"""
Pydantic models (schemas) for API request/response validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Enums
# =============================================================================


class TaskStatus(str, Enum):
    """Status of an async rendering task."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    DEGRADED = "degraded"


class ComplianceLevel(str, Enum):
    """Compliance validation result level."""

    COMPLIANT = "compliant"
    WARNING = "warning"
    BLOCKED = "blocked"


# =============================================================================
# Request Models
# =============================================================================


class DiagramGenerateRequest(BaseModel):
    """Request to generate a diagram from Draw.io XML."""

    xml_content: str = Field(
        ...,
        min_length=1,
        max_length=10_485_760,  # 10 MB
        description="Raw Draw.io XML content (mxGraphModel format).",
        json_schema_extra={"example": '<mxGraphModel><root><mxCell id="0"/></root></mxGraphModel>'},
    )
    export_format: str = Field(
        default="svg",
        pattern=r"^(svg|png|pdf)$",
        description="Export format: svg, png, or pdf.",
    )
    export_scale: float = Field(
        default=1.0,
        ge=0.1,
        le=4.0,
        description="Export scale factor (0.1 to 4.0).",
    )
    webhook_url: Optional[str] = Field(
        default=None,
        max_length=2048,
        description="URL to notify when rendering completes. Overrides default webhook.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata to include in webhook callback.",
    )
    task_id: Optional[str] = Field(
        default=None,
        description="Client-provided task ID. Auto-generated if not provided.",
    )

    @field_validator("export_format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        allowed = {"svg", "png", "pdf"}
        if v.lower() not in allowed:
            raise ValueError(f"Export format must be one of: {', '.join(sorted(allowed))}")
        return v.lower()


# =============================================================================
# Compliance Models
# =============================================================================


class ColorViolation(BaseModel):
    """A single color violation found in the XML."""

    color_hex: str = Field(..., description="Hex color that violates policy (e.g., FF0000).")
    attribute_name: str = Field(..., description="XML attribute where the color was found (e.g., fillColor).")
    element_id: Optional[str] = Field(None, description="mxCell id containing the violation.")


class StencilViolation(BaseModel):
    """A single stencil violation found in the XML."""

    stencil_id: str = Field(..., description="Stencil ID that is not allowed (e.g., leanix).")
    element_id: Optional[str] = Field(None, description="mxCell id using the disallowed stencil.")


class ComplianceCheck(BaseModel):
    """Result of a compliance validation check."""

    level: ComplianceLevel = Field(..., description="Overall compliance level.")
    xml_well_formed: bool = Field(default=True, description="Whether XML is well-formed.")
    stencils_detected: list[str] = Field(default_factory=list, description="Stencil IDs found in the XML.")
    stencil_violations: list[StencilViolation] = Field(default_factory=list, description="Stencil policy violations.")
    color_violations: list[ColorViolation] = Field(default_factory=list, description="Color policy violations.")
    requires_archimate_license: bool = Field(default=False, description="Whether ArchiMate stencils were detected.")
    archimate_license_valid: bool = Field(default=False, description="Whether a valid ArchiMate license is configured.")
    errors: list[str] = Field(default_factory=list, description="Validation error messages.")


# =============================================================================
# Response Models
# =============================================================================


class DiagramGenerateResponse(BaseModel):
    """Response to a diagram generation request."""

    task_id: str = Field(..., description="Unique task identifier.")
    status: TaskStatus = Field(..., description="Initial task status (queued or rejected).")
    compliance: Optional[ComplianceCheck] = Field(None, description="Compliance check result (if validation was performed).")
    message: str = Field(default="", description="Human-readable status message.")


class TaskStatusResponse(BaseModel):
    """Response to a task status query."""

    task_id: str = Field(..., description="Task identifier.")
    status: TaskStatus = Field(..., description="Current task status.")
    result: Optional[dict[str, Any]] = Field(None, description="Task result (available when completed).")
    error: Optional[str] = Field(None, description="Error message (available when failed).")
    created_at: Optional[datetime] = Field(None, description="Task creation timestamp.")
    updated_at: Optional[datetime] = Field(None, description="Last status update timestamp.")
    message: str = Field(default="", description="Human-readable status message.")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(default="healthy", description="Service health status.")
    version: str = Field(default="0.1.0", description="API version.")
    redis_connected: bool = Field(default=False, description="Whether Redis is reachable.")
    uptime_seconds: Optional[float] = Field(None, description="Process uptime in seconds.")


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error type/code.")
    message: str = Field(..., description="Human-readable error message.")
    detail: Optional[list[dict[str, Any]]] = Field(None, description="Additional error details.")
    task_id: Optional[str] = Field(None, description="Task ID if the error relates to a specific task.")