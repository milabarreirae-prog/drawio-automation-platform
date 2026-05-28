"""
Data models and enums for the rendering worker.

Defines task result types, failure categories, degradation modes,
and the FallbackReport used for webhook notifications.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# =============================================================================
# Enums
# =============================================================================


class TaskStatus(str, Enum):
    """Status of an async rendering task (mirrors API schemas)."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    DEGRADED = "degraded"


class FailureCategory(str, Enum):
    """
    Classification of rendering failures.

    Determines retry behavior:
    - Non-retryable: INVALID_XML, POLICY_VIOLATION, LICENSE_MISSING
    - Retryable: RENDER_TIMEOUT, OOM_KILLED, NODE_CRASH
    - Non-retryable: STENCIL_FETCH_FAILED, S3_UPLOAD_FAILED, WEBHOOK_FAILED
    """

    INVALID_XML = "invalid_xml"          # XML parsing error — do NOT retry
    POLICY_VIOLATION = "policy_violation" # Color/stencil compliance violation — do NOT retry
    LICENSE_MISSING = "license_missing"   # ArchiMate license required — do NOT retry
    RENDER_TIMEOUT = "render_timeout"     # Draw.io CLI timeout — retryable
    OOM_KILLED = "oom_killed"             # Out of memory — retryable
    NODE_CRASH = "node_crash"             # Chromium crash — retryable
    STENCIL_FETCH_FAILED = "stencil_fetch_failed"  # Could not resolve stencils
    S3_UPLOAD_FAILED = "s3_upload_failed"           # S3/MinIO upload error
    WEBHOOK_FAILED = "webhook_failed"               # Webhook delivery error
    UNKNOWN = "unknown"                            # Unclassified error


class DegradationMode(str, Enum):
    """Modes of degraded rendering when full compliance rendering is impossible."""

    NONE = "none"               # No degradation — full render succeeded
    PLACEHOLDER = "placeholder"  # Stencils replaced with basic shapes
    CACHED_ONLY = "cached_only"  # Only cached stencils used (offline mode)
    STENCIL_STRIPPED = "stencil_stripped"  # Stencils removed, basic shapes only
    COLOR_DEFAULT = "color_default"  # Non-compliant colors replaced with defaults


class ComplianceLevel(str, Enum):
    """Compliance validation result level."""

    COMPLIANT = "compliant"
    WARNING = "warning"
    BLOCKED = "blocked"


# Mapping of failure categories to retry eligibility
RETRYABLE_FAILURES: frozenset = frozenset({
    FailureCategory.RENDER_TIMEOUT,
    FailureCategory.OOM_KILLED,
    FailureCategory.NODE_CRASH,
})

NON_RETRYABLE_FAILURES: frozenset = frozenset({
    FailureCategory.INVALID_XML,
    FailureCategory.POLICY_VIOLATION,
    FailureCategory.LICENSE_MISSING,
    FailureCategory.STENCIL_FETCH_FAILED,
    FailureCategory.S3_UPLOAD_FAILED,
    FailureCategory.WEBHOOK_FAILED,
    FailureCategory.UNKNOWN,
})

# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class StencilResolutionResult:
    """Result of attempting to resolve stencil libraries for rendering."""

    success: bool = True
    libraries_param: str = ""  # The --libraries argument for draw.io CLI
    xml_enriched: str = ""  # XML with <mxLibrary> injected if needed
    resolved_stencils: list[str] = field(default_factory=list)
    missing_stencils: list[str] = field(default_factory=list)
    degradation_mode: DegradationMode = DegradationMode.NONE
    warnings: list[str] = field(default_factory=list)


@dataclass
class ExportResult:
    """Result of a rendering export operation."""

    success: bool = False
    file_path: str = ""  # Local file path of the exported file
    s3_url: str = ""  # S3 presigned URL (if upload succeeded)
    s3_key: str = ""  # S3 object key
    export_format: str = "svg"
    file_size_bytes: int = 0
    degradation_mode: DegradationMode = DegradationMode.NONE
    warnings: list[str] = field(default_factory=list)


@dataclass
class FallbackReport:
    """
    Comprehensive report of a rendering task execution.

    Used to generate webhook payloads and track degradation decisions.
    Tracks the full lifecycle: stencil resolution → rendering → S3 upload.
    """

    task_id: str = ""
    status: TaskStatus = TaskStatus.PROCESSING
    degradation_mode: DegradationMode = DegradationMode.NONE
    failure_category: Optional[FailureCategory] = None
    export_result: Optional[ExportResult] = None

    # Timings
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # Stencil information
    stencils_resolved: list[str] = field(default_factory=list)
    stencils_missing: list[str] = field(default_factory=list)
    used_placeholders: bool = False

    # Error details
    error_message: str = ""
    error_stderr: str = ""
    retry_count: int = 0
    max_retries: int = 2

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def should_retry(self) -> bool:
        """Determine if the task should be retried based on failure category."""
        if self.failure_category is None:
            return False
        return (
            self.failure_category in RETRYABLE_FAILURES
            and self.retry_count < self.max_retries
        )

    def to_webhook_payload(self) -> dict[str, Any]:
        """Generate a webhook-compatible JSON payload from this report."""
        payload: dict[str, Any] = {
            "event": f"diagram.{self.status.value}",
            "task_id": self.task_id,
            "status": self.status.value,
            "degradation": self.degradation_mode.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "retry_count": self.retry_count,
            "metadata": self.metadata,
        }

        if self.export_result and self.export_result.success:
            payload["result"] = {
                "s3_url": self.export_result.s3_url,
                "s3_key": self.export_result.s3_key,
                "format": self.export_result.export_format,
                "file_size_bytes": self.export_result.file_size_bytes,
            }
            payload["warnings"] = self.export_result.warnings

        if self.stencils_resolved:
            payload["stencils"] = {
                "resolved": self.stencils_resolved,
                "missing": self.stencils_missing,
                "used_placeholders": self.used_placeholders,
            }

        if self.error_message:
            payload["error"] = {
                "message": self.error_message,
                "category": self.failure_category.value if self.failure_category else "unknown",
                "retryable": self.should_retry(),
            }

        return payload