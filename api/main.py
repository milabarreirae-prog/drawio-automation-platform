"""
FastAPI REST API for drawio-automation-platform.

Endpoints:
  GET  /health                      — Health check
  POST /api/v1/diagram/generate     — Submit diagram for rendering
  GET  /api/v1/diagram/status/{id}  — Check rendering task status

Architecture:
  - XML validation via XMLLinter (compliance check)
  - Task enqueuing via ARQ (Async Redis Queue)
  - BackgroundTasks PROHIBITED for rendering — always ARQ
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import Settings, get_settings
from api.linting import XMLLinter
from api.schemas import (
    ComplianceCheck,
    DiagramGenerateRequest,
    DiagramGenerateResponse,
    ErrorResponse,
    HealthResponse,
    TaskStatus,
    TaskStatusResponse,
)

# ============================================================================
# Application State
# ============================================================================

settings: Settings = get_settings()
logger = logging.getLogger("api")
_start_time: float = time.time()

# Global ARQ pool (initialized in lifespan)
arq_pool: Optional[ArqRedis] = None


# ============================================================================
# Lifespan — Redis and ARQ Connection
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    On startup: Connect to Redis, create ARQ pool.
    On shutdown: Close ARQ pool, disconnect Redis.
    """
    global arq_pool
    logger.info("Starting drawio-automation-platform API v0.1.0")

    # Connect to Redis for ARQ
    try:
        redis_settings = RedisSettings(
            host=settings.redis_host,
            port=settings.redis_port,
            database=settings.redis_db,
            password=settings.redis_password,
        )
        arq_pool = await create_pool(redis_settings)
        # Verify connection
        await arq_pool.ping()
        logger.info("Connected to Redis at %s:%d", settings.redis_host, settings.redis_port)
    except Exception as e:
        logger.error("Failed to connect to Redis: %s", e)
        arq_pool = None

    yield  # Application runs here

    # Shutdown
    if arq_pool:
        await arq_pool.close()
        logger.info("Closed ARQ pool")

    logger.info("API server shutting down")


# ============================================================================
# FastAPI Application
# ============================================================================


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="drawio-automation-platform",
        description="Enterprise Draw.io automation platform with API, async rendering, and compliance validation",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Custom middleware for request logging
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        logger.debug("[%s] %s %s", request_id, request.method, request.url.path)

        start = time.monotonic()
        response = await call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000

        logger.debug(
            "[%s] %s %s → %d (%.1fms)",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response

    # Exception handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error="http_error",
                message=str(exc.detail),
                detail=exc.headers if exc.headers else None,
            ).model_dump(),
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error="validation_error",
                message=str(exc),
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="internal_error",
                message="An unexpected error occurred. Check server logs for details.",
            ).model_dump(),
        )

    return app


app = create_app()


# ============================================================================
# GET /health
# ============================================================================


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.

    Returns service status including Redis connectivity.
    """
    redis_ok = False
    if arq_pool:
        try:
            await arq_pool.ping()
            redis_ok = True
        except Exception:
            redis_ok = False

    return HealthResponse(
        status="healthy" if redis_ok else "degraded",
        version="0.1.0",
        redis_connected=redis_ok,
        uptime_seconds=round(time.time() - _start_time, 1),
    )


# ============================================================================
# POST /api/v1/diagram/generate
# ============================================================================


@app.post("/api/v1/diagram/generate", response_model=DiagramGenerateResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_diagram(request: DiagramGenerateRequest) -> DiagramGenerateResponse:
    """
    Submit a Draw.io diagram for headless rendering.

    Flow:
    1. Validate XML compliance (colors, stencils, licenses)
    2. If BLOCKED → return 202 with status REJECTED and compliance details
    3. If compliant → enqueue ARQ task → return 202 with task_id

    The actual rendering happens asynchronously in the worker.
    BackgroundTasks are PROHIBITED for rendering.
    """
    if arq_pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Task queue (Redis/ARQ) is not available",
        )

    # Step 1: Compliance validation
    linter = XMLLinter(settings)
    compliance = linter.full_validation(request.xml_content)

    # Step 2: Generate task ID
    task_id = request.task_id or str(uuid.uuid4())

    # Step 3: If blocked, reject immediately (still return 202 with status)
    if compliance.level.value == "blocked":
        logger.warning(
            "Task %s REJECTED: compliance=%s, errors=%s",
            task_id,
            compliance.level.value,
            compliance.errors,
        )
        return DiagramGenerateResponse(
            task_id=task_id,
            status=TaskStatus.REJECTED,
            compliance=compliance,
            message=f"Diagram rejected due to compliance violations: {'; '.join(compliance.errors)}",
        )

    # Step 4: Enqueue ARQ task (NO BackgroundTasks!)
    try:
        job = await arq_pool.enqueue_job(
            "render_drawio",
            task_id=task_id,
            xml_content=request.xml_content,
            export_format=request.export_format,
            export_scale=request.export_scale,
            webhook_url=request.webhook_url or settings.webhook_default_url,
            metadata=request.metadata,
        )
        logger.info("Task %s QUEUED (job_id=%s)", task_id, job.job_id)
    except Exception as e:
        logger.error("Failed to enqueue task %s: %s", task_id, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue rendering task. Try again later.",
        ) from e

    return DiagramGenerateResponse(
        task_id=task_id,
        status=TaskStatus.QUEUED,
        compliance=compliance,
        message=f"Diagram queued for rendering. Check status at /api/v1/diagram/status/{task_id}",
    )


# ============================================================================
# GET /api/v1/diagram/status/{task_id}
# ============================================================================


@app.get("/api/v1/diagram/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """
    Get the status of a rendering task by its ID.

    Queries ARQ job result from Redis.
    """
    if arq_pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Task queue is not available",
        )

    try:
        # Query ARQ for job status
        job_info = await arq_pool.get_job_result(task_id)

        if job_info is None:
            # Check if it's queued but not yet processed
            # ARQ auto-generates job IDs; we store task_id separately
            # For simplicity, return queued if not found (may need Redis lookup)
            logger.debug("Task %s not found in completed/failed jobs — may still be queued", task_id)
            return TaskStatusResponse(
                task_id=task_id,
                status=TaskStatus.QUEUED,
                message="Task is queued and waiting for a worker.",
            )

        # Parse ARQ result
        if job_info.success:
            result = job_info.result
            if isinstance(result, dict):
                return TaskStatusResponse(
                    task_id=task_id,
                    status=TaskStatus.COMPLETED if result.get("status") != "degraded" else TaskStatus.DEGRADED,
                    result=result,
                    message=result.get("message", "Rendering completed."),
                )
            return TaskStatusResponse(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                result={"data": str(result)},
                message="Rendering completed.",
            )

        # Job failed
        return TaskStatusResponse(
            task_id=task_id,
            status=TaskStatus.FAILED,
            error=str(job_info.result) if job_info.result else "Unknown error",
            message="Rendering failed. Check error details.",
        )

    except Exception as e:
        logger.error("Error querying task %s: %s", task_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query task status: {e}",
        ) from e


# ============================================================================
# GET / — Root redirect to docs
# ============================================================================


@app.get("/")
async def root():
    """Root endpoint — redirects to API docs."""
    return {
        "service": "drawio-automation-platform",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }