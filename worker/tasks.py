"""
ARQ Worker Tasks for Rendering Draw.io Diagrams.

Main task: render_drawio()
  - Stencil resolution (with fallback)
  - Draw.io CLI execution (with retry for transient failures)
  - S3/MinIO upload
  - Webhook notification

WorkerSettings configured with retry_jobs=False (manual retry via _execute_render_with_retry).
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from arq.connections import RedisSettings
from arq.worker import run_worker

from api.config import Settings, get_settings
from worker.models import (
    DegradationMode,
    ExportResult,
    FailureCategory,
    FallbackReport,
    RETRYABLE_FAILURES,
    StencilResolutionResult,
    TaskStatus,
)
from worker.s3_uploader import S3Uploader
from worker.stencils_loader import StencilsLoader
from worker.webhooks import WebhookNotifier

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

settings: Settings = get_settings()

# =============================================================================
# Failure Classification
# =============================================================================


def classify_render_failure(stderr: str) -> FailureCategory:
    """
    Classify a rendering failure from Draw.io CLI stderr output.

    Args:
        stderr: Standard error output from the drawio CLI process.

    Returns:
        FailureCategory enum value.
    """
    stderr_lower = stderr.lower() if stderr else ""

    # Order matters — more specific patterns first
    if "invalid xml" in stderr_lower or "xml parse error" in stderr_lower:
        return FailureCategory.INVALID_XML
    if "policy violation" in stderr_lower or "not allowed" in stderr_lower:
        return FailureCategory.POLICY_VIOLATION
    if "license" in stderr_lower and ("missing" in stderr_lower or "required" in stderr_lower or "archimate" in stderr_lower):
        return FailureCategory.LICENSE_MISSING
    if "out of memory" in stderr_lower or "oom" in stderr_lower or "killed" in stderr_lower:
        return FailureCategory.OOM_KILLED
    if "timeout" in stderr_lower or "timed out" in stderr_lower:
        return FailureCategory.RENDER_TIMEOUT
    if "segfault" in stderr_lower or "signal" in stderr_lower or "crash" in stderr_lower:
        return FailureCategory.NODE_CRASH
    if "stencil" in stderr_lower and ("fetch" in stderr_lower or "download" in stderr_lower or "not found" in stderr_lower):
        return FailureCategory.STENCIL_FETCH_FAILED
    if "s3" in stderr_lower and ("upload" in stderr_lower or "failed" in stderr_lower):
        return FailureCategory.S3_UPLOAD_FAILED
    if "webhook" in stderr_lower and ("failed" in stderr_lower or "error" in stderr_lower):
        return FailureCategory.WEBHOOK_FAILED

    return FailureCategory.UNKNOWN


# =============================================================================
# Render Execution with Retry
# =============================================================================


async def _execute_render_with_retry(
    xml_content: str,
    export_format: str,
    export_scale: float,
    libraries_param: str,
    task_id: str,
    report: FallbackReport,
) -> tuple[str | None, str, FailureCategory | None]:
    """
    Execute drawio CLI render with retry logic for transient failures.

    Only retries transient failures: RENDER_TIMEOUT, OOM_KILLED, NODE_CRASH.
    Non-retryable failures (INVALID_XML, POLICY, LICENSE) abort immediately.

    Returns:
        Tuple of (output_file_path or None, stderr, failure_category or None).
    """
    max_retries = settings.worker_render_max_retries
    backoff_base = settings.worker_render_retry_backoff

    for attempt in range(max_retries + 1):
        report.retry_count = attempt

        if attempt > 0:
            backoff = backoff_base ** attempt
            logger.info("Task %s: Retry %d/%d (backoff: %ds)", task_id, attempt, max_retries, backoff)
            await asyncio.sleep(backoff)

        try:
            output_path, stderr = await _run_drawio_cli(
                xml_content=xml_content,
                export_format=export_format,
                export_scale=export_scale,
                libraries_param=libraries_param,
                task_id=task_id,
            )

            if output_path:
                return output_path, stderr, None

            # Render failed — classify and decide retry
            category = classify_render_failure(stderr)

            if category in RETRYABLE_FAILURES and attempt < max_retries:
                logger.warning("Task %s: Transient failure (%s) — will retry", task_id, category.value)
                continue
            else:
                logger.error("Task %s: Non-retryable failure (%s) or max retries reached", task_id, category.value)
                return None, stderr, category

        except Exception as e:
            logger.exception("Task %s: Unexpected error during render attempt %d", task_id, attempt)
            if attempt < max_retries:
                continue
            return None, str(e), FailureCategory.UNKNOWN

    return None, "Max retries exhausted", FailureCategory.UNKNOWN


async def _run_drawio_cli(
    xml_content: str,
    export_format: str,
    export_scale: float,
    libraries_param: str,
    task_id: str,
) -> tuple[str | None, str]:
    """
    Execute the drawio CLI to render a diagram.

    Writes XML to a temp file, runs drawio, and returns the output path.
    Uses Chromium flags from settings.
    """
    drawio_cli = settings.drawio_cli_path
    timeout = settings.worker_job_timeout

    # Write XML to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8", prefix=f"drawio_{task_id[:8]}_") as xml_file:
        xml_file.write(xml_content)
        xml_path = xml_file.name

    # Output path
    output_path = tempfile.mktemp(suffix=f".{export_format}", prefix=f"drawio_output_{task_id[:8]}_")

    # Build command
    cmd = [
        drawio_cli,
        "--export",
        "--format", export_format,
        "--scale", str(export_scale),
        "--output", output_path,
        xml_path,
    ]

    # Add libraries parameter if present
    if libraries_param:
        cmd.extend(["--libraries", libraries_param])

    # Add Chromium flags via environment
    env = os.environ.copy()
    env["ELECTRON_DISABLE_SANDBOX"] = "1"
    if settings.chromium_flags:
        env["CHROMIUM_USER_FLAGS"] = settings.chromium_flags

    logger.debug("Task %s: Running drawio CLI: %s", task_id, " ".join(cmd))

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

        if process.returncode == 0 and Path(output_path).exists():
            logger.info("Task %s: Render completed successfully (%s, %.1f KB)", task_id, export_format, Path(output_path).stat().st_size / 1024)
            return output_path, stderr_text

        logger.error("Task %s: Render failed (rc=%d): %s", task_id, process.returncode, stderr_text[:500])
        return None, stderr_text

    except asyncio.TimeoutError:
        logger.error("Task %s: Render timeout after %ds", task_id, timeout)
        return None, f"Timeout after {timeout}s"

    except Exception as e:
        logger.exception("Task %s: Render exception: %s", task_id, e)
        return None, str(e)

    finally:
        # Clean up XML temp file
        try:
            Path(xml_path).unlink(missing_ok=True)
        except Exception:
            pass


# ============================================================================
# Main ARQ Task: render_drawio
# ============================================================================


async def render_drawio(
    ctx: dict[str, Any],
    task_id: str,
    xml_content: str,
    export_format: str = "svg",
    export_scale: float = 1.0,
    webhook_url: str = "",
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Main ARQ task for rendering a Draw.io diagram.

    Flow:
    1. Resolve stencils (with fallback/block decision)
    2. If BLOCKED → abort and return blocked status
    3. Execute drawio CLI (with retry for transient failures)
    4. Upload result to S3/MinIO
    5. Send webhook notification
    6. Return result dict (stored in Redis by ARQ)

    Args:
        ctx: ARQ job context (Redis connection, etc.).
        task_id: Unique task identifier.
        xml_content: Raw Draw.io XML content.
        export_format: Output format (svg, png, pdf).
        export_scale: Export scale factor.
        webhook_url: URL to notify on completion.
        metadata: Optional metadata to include in webhook.

    Returns:
        Dict with task result (stored in Redis result backend).
    """
    report = FallbackReport(
        task_id=task_id,
        status=TaskStatus.PROCESSING,
        max_retries=settings.worker_render_max_retries,
        started_at=datetime.now(timezone.utc).isoformat(),
        metadata=metadata or {},
    )

    logger.info("Task %s: Starting render (format=%s, scale=%.1f)", task_id, export_format, export_scale)

    # ── Step 1: Stencil Resolution ────────────────────────────────────────
    stencils_loader = StencilsLoader(
        allowed_stencils=settings.allowed_stencils_list,
        archimate_license=settings.has_archimate_license,
    )

    # Detect required stencils from XML
    from api.linting import detect_stencils
    from lxml import etree

    try:
        root = etree.fromstring(xml_content.encode("utf-8"), parser=etree.XMLParser(recover=True))
        required_stencils = list(detect_stencils(root)) if xml_content else []
    except Exception:
        required_stencils = []

    stencil_result = stencils_loader.process_xml_with_fallback(xml_content, required_stencils)

    report.stencils_resolved = stencil_result.resolved_stencils
    report.stencils_missing = stencil_result.missing_stencils
    report.degradation_mode = stencil_result.degradation_mode

    # ── Step 2: Check if Blocked ──────────────────────────────────────────
    if not stencil_result.success:
        logger.warning("Task %s: BLOCKED — stencil resolution failed: %s", task_id, stencil_result.warnings)
        report.status = TaskStatus.REJECTED
        report.failure_category = FailureCategory.LICENSE_MISSING if any("ArchiMate" in w for w in stencil_result.warnings) else FailureCategory.POLICY_VIOLATION
        report.error_message = "; ".join(stencil_result.warnings)
        report.completed_at = datetime.now(timezone.utc).isoformat()

        # Send webhook for blocked
        if webhook_url:
            notifier = WebhookNotifier()
            await notifier.notify(webhook_url, report)

        return report.to_webhook_payload()

    # ── Step 3: Render with Retry ─────────────────────────────────────────
    enriched_xml = stencil_result.xml_enriched or xml_content
    libraries_param = stencil_result.libraries_param

    output_path, stderr, failure_cat = await _execute_render_with_retry(
        xml_content=enriched_xml,
        export_format=export_format,
        export_scale=export_scale,
        libraries_param=libraries_param,
        task_id=task_id,
        report=report,
    )

    if failure_cat or not output_path:
        report.status = TaskStatus.FAILED
        report.failure_category = failure_cat or FailureCategory.UNKNOWN
        report.error_message = stderr[:1000]
        report.error_stderr = stderr
        report.completed_at = datetime.now(timezone.utc).isoformat()

        if webhook_url:
            notifier = WebhookNotifier()
            await notifier.notify(webhook_url, report)

        if output_path:
            try:
                Path(output_path).unlink(missing_ok=True)
            except Exception:
                pass

        return report.to_webhook_payload()

    # ── Step 4: S3 Upload ─────────────────────────────────────────────────
    try:
        uploader = S3Uploader()
        s3_url, s3_key = await uploader.upload(
            file_path=output_path,
            task_id=task_id,
            export_format=export_format,
        )

        file_size = Path(output_path).stat().st_size

        report.export_result = ExportResult(
            success=True,
            file_path=output_path,
            s3_url=s3_url,
            s3_key=s3_key,
            export_format=export_format,
            file_size_bytes=file_size,
            degradation_mode=report.degradation_mode,
            warnings=stencil_result.warnings,
        )

        # Determine final status
        if report.degradation_mode != DegradationMode.NONE:
            report.status = TaskStatus.DEGRADED
        else:
            report.status = TaskStatus.COMPLETED

        logger.info("Task %s: COMPLETED — S3 URL: %s", task_id, s3_url[:100])

    except Exception as e:
        logger.exception("Task %s: S3 upload failed: %s", task_id, e)
        report.status = TaskStatus.FAILED
        report.failure_category = FailureCategory.S3_UPLOAD_FAILED
        report.error_message = f"S3 upload failed: {e}"
        report.completed_at = datetime.now(timezone.utc).isoformat()

        if webhook_url:
            notifier = WebhookNotifier()
            await notifier.notify(webhook_url, report)

        try:
            Path(output_path).unlink(missing_ok=True)
        except Exception:
            pass

        return report.to_webhook_payload()

    # ── Step 5: Webhook Notification ──────────────────────────────────────
    report.completed_at = datetime.now(timezone.utc).isoformat()

    if webhook_url:
        notifier = WebhookNotifier()
        await notifier.notify(webhook_url, report)

    # Clean up local output file after upload
    try:
        Path(output_path).unlink(missing_ok=True)
    except Exception:
        pass

    return report.to_webhook_payload()


# ============================================================================
# Worker Configuration for ARQ
# ============================================================================


class WorkerSettings:
    """
    ARQ Worker Settings.

    Configures Redis connection, job timeout, and task functions.
    retry_jobs is set to False because retry logic is handled
    manually in _execute_render_with_retry for more granular control.
    """

    redis_settings = RedisSettings(
        host=settings.redis_host,
        port=settings.redis_port,
        database=settings.redis_db,
        password=settings.redis_password,
        retry_on_timeout=settings.redis_retry_on_timeout,
    )

    # Task functions registered with the worker
    functions: list = [render_drawio]

    # Job execution settings
    job_timeout = settings.worker_job_timeout
    max_jobs = settings.worker_max_jobs
    retry_jobs = False  # Manual retry via _execute_render_with_retry
    health_check_interval = settings.arq_health_check_interval
    keep_result = settings.arq_expires
    allow_abort_jobs = True


# ============================================================================
# Worker Entry Point
# ============================================================================


def main() -> None:
    """Start the ARQ worker process."""
    logger.info("Starting ARQ worker...")
    logger.info("Redis: %s:%d", settings.redis_host, settings.redis_port)
    logger.info("Max concurrent jobs: %d", settings.worker_max_jobs)
    logger.info("Job timeout: %ds", settings.worker_job_timeout)

    run_worker(WorkerSettings)


if __name__ == "__main__":
    main()