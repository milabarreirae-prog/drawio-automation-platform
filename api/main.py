"""
API REST del normalizador C4 (drawio-automation-platform).

Endpoints:
  GET  /health                        — Estado del servicio + motor de layout
  GET  /metrics                       — Métricas Prometheus
  POST /api/v1/diagram/normalize      — XML crudo → C4 (síncrono)
  POST /api/v1/diagram/from-image     — Imagen + prompt → C4 (visión LLM)
"""

from __future__ import annotations

import base64
import datetime
import hmac
import logging
import time
import uuid
from collections import defaultdict, deque
from threading import Lock

from cachetools import LRUCache
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from api.config import Settings, get_settings
from api.linting import XMLLinter
from api.schemas import (
    ErrorResponse,
    FromImageRequest,
    HealthResponse,
    NormalizeReportModel,
    NormalizeRequest,
    NormalizeResponse,
    TitleBlockInput,
)
from c4norm.layout.elk import ElkLayout
from c4norm.normalize import normalize
from c4norm.sheet import TitleBlock
from c4norm.vision import VisionExtractor, extract_level_from_prompt

# =============================================================================
# Estado de la aplicación
# =============================================================================

settings: Settings = get_settings()
logger = logging.getLogger("api")
_start_time: float = time.time()

_rate_limit_lock = Lock()
_rate_limit_events: LRUCache = LRUCache(maxsize=50_000)
_RATE_LIMIT_WINDOW_SECONDS = 60

_metrics_lock = Lock()
_http_requests_total: dict[tuple[str, str, int], int] = defaultdict(int)
_http_request_latency_seconds_sum: dict[tuple[str, str], float] = defaultdict(float)
_http_request_latency_seconds_count: dict[tuple[str, str], int] = defaultdict(int)


# =============================================================================
# Seguridad / rate limiting
# =============================================================================


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _enforce_api_key(request: Request) -> None:
    """Exige API key solo si se configuró una."""
    if not settings.api_key:
        return
    token = _extract_bearer_token(request.headers.get("Authorization"))
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Use Bearer <api_key>",
        )
    if not hmac.compare_digest(token.encode(), settings.api_key.encode()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for.strip():
        # Truncar a 45 chars (longitud máxima de IPv6) para evitar claves gigantes.
        return forwarded_for.split(",", maxsplit=1)[0].strip()[:45]
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _enforce_rate_limit(request: Request, *, limit: int, bucket: str) -> None:
    """Límite por IP/endpoint en ventana fija, en memoria."""
    if not settings.rate_limit_enabled or limit <= 0:
        return
    now = time.monotonic()
    window_start = now - _RATE_LIMIT_WINDOW_SECONDS
    key = f"{bucket}:{_client_ip(request)}"
    with _rate_limit_lock:
        events = _rate_limit_events.get(key)
        if events is None:
            events = deque()
            _rate_limit_events[key] = events
        while events and events[0] < window_start:
            events.popleft()
        if len(events) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {bucket}. Max {limit} requests per minute.",
            )
        events.append(now)


def _clear_rate_limit_state() -> None:
    """Reinicia los buckets de rate limit (utilidad de tests)."""
    with _rate_limit_lock:
        _rate_limit_events.clear()


# =============================================================================
# Métricas
# =============================================================================


def _record_http_metrics(method: str, path: str, status_code: int, elapsed_seconds: float) -> None:
    with _metrics_lock:
        _http_requests_total[(method, path, status_code)] += 1
        _http_request_latency_seconds_sum[(method, path)] += elapsed_seconds
        _http_request_latency_seconds_count[(method, path)] += 1


def _build_prometheus_metrics_text() -> str:
    lines: list[str] = [
        "# HELP drawio_http_requests_total Total HTTP requests.",
        "# TYPE drawio_http_requests_total counter",
    ]
    with _metrics_lock:
        for (method, path, status_code), value in sorted(_http_requests_total.items()):
            lines.append(
                f'drawio_http_requests_total{{method="{method}",path="{path}",status_code="{status_code}"}} {value}'
            )
        lines.extend([
            "# HELP drawio_http_request_duration_seconds_sum Cumulative HTTP request duration in seconds.",
            "# TYPE drawio_http_request_duration_seconds_sum counter",
        ])
        for (method, path), value in sorted(_http_request_latency_seconds_sum.items()):
            lines.append(f'drawio_http_request_duration_seconds_sum{{method="{method}",path="{path}"}} {value:.6f}')
        lines.extend([
            "# HELP drawio_http_request_duration_seconds_count Total observed HTTP requests for latency.",
            "# TYPE drawio_http_request_duration_seconds_count counter",
        ])
        for (method, path), value in sorted(_http_request_latency_seconds_count.items()):
            lines.append(f'drawio_http_request_duration_seconds_count{{method="{method}",path="{path}"}} {value}')
    lines.append("")
    return "\n".join(lines)


def _layout_engine() -> str:
    """Reporta el motor de layout disponible ('elk' si hay Node + elkjs)."""
    try:
        return "elk" if ElkLayout().available() else "layered"
    except Exception:
        return "layered"


def _build_title_block(data: TitleBlockInput | None) -> TitleBlock | None:
    """Construye un TitleBlock del cajetín; None si no hay título (usa el del diagrama)."""
    if data is None or not (data.title and data.title.strip()):
        return None
    fields: dict[str, str] = {"title": data.title}
    if data.project is not None:
        fields["project"] = data.project
    if data.doc_type is not None:
        fields["doc_type"] = data.doc_type
    if data.drawn_by is not None:
        fields["drawn_by"] = data.drawn_by
    if data.approved_by is not None:
        fields["approved_by"] = data.approved_by
    if data.revision is not None:
        fields["revision"] = data.revision
    fields["date"] = data.date or datetime.date.today().isoformat()
    return TitleBlock(**fields)


# =============================================================================
# Aplicación FastAPI
# =============================================================================


def create_app() -> FastAPI:
    app = FastAPI(
        title="drawio-automation-platform",
        description="Normaliza Draw.io crudo a C4 conforme a estándar (XML → XML).",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        start = time.monotonic()
        response = await call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.debug(
            "[%s] %s %s -> %d (%.1fms)",
            request_id, request.method, request.url.path, response.status_code, elapsed_ms,
        )
        _record_http_metrics(request.method, request.url.path, response.status_code, elapsed_ms / 1000)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(error="http_error", message=str(exc.detail)).model_dump(),
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(error="validation_error", message=str(exc)).model_dump(),
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


# =============================================================================
# Endpoints
# =============================================================================


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Estado del servicio y motor de layout disponible."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        layout_engine=_layout_engine(),
        uptime_seconds=round(time.time() - _start_time, 1),
    )


@app.get("/metrics")
async def metrics() -> PlainTextResponse:
    """Métricas en formato de exposición Prometheus."""
    return PlainTextResponse(content=_build_prometheus_metrics_text(), media_type="text/plain; version=0.0.4")


@app.post("/api/v1/diagram/normalize", response_model=NormalizeResponse)
def normalize_diagram(payload: NormalizeRequest, request: Request) -> NormalizeResponse:
    """
    Normaliza un Draw.io crudo a C4 (síncrono).

    1. Autenticación + rate limit + límite de tamaño.
    2. ``c4norm.normalize`` → XML C4 + reporte.
    3. (opcional) compliance sobre el XML de salida.
    """
    _enforce_api_key(request)
    _enforce_rate_limit(request, limit=settings.rate_limit_normalize_per_minute, bucket="normalize")

    payload_size = len(payload.xml_content.encode("utf-8"))
    if payload_size > settings.max_xml_payload_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"XML payload too large: {payload_size} bytes. Maximum is {settings.max_xml_payload_size}.",
        )

    title_block = _build_title_block(payload.title_block)

    # normalize() lanza ValueError si el XML no contiene un diagrama -> 422.
    xml_c4, report = normalize(
        payload.xml_content,
        c4_level=payload.c4_level,
        classifier=payload.classifier,
        title_block=title_block,
    )

    compliance = None
    if payload.run_compliance_check:
        compliance = XMLLinter(settings).full_validation(xml_c4)

    return NormalizeResponse(
        xml_c4=xml_c4,
        report=NormalizeReportModel(**report.to_api_dict()),
        compliance=compliance,
    )


@app.post("/api/v1/diagram/from-image", response_model=NormalizeResponse)
def diagram_from_image(payload: FromImageRequest, request: Request) -> NormalizeResponse:
    """
    Genera un diagrama C4 desde una imagen + prompt en lenguaje natural.

    Pipeline:
    1. Autenticación + rate limit.
    2. Detecta el nivel C4 del prompt (si no se indica explícitamente).
    3. ``VisionExtractor`` (LLM con visión) → XML Draw.io crudo.
    4. ``c4norm.normalize()`` → XML C4 + reporte.
    5. (opcional) compliance sobre el XML de salida.

    Requiere ``C4NORM_LLM_API_KEY`` y un modelo de visión (``C4NORM_VISION_MODEL``).
    Proveedor por defecto: Alibaba Cloud MaaS ``qwen-image-2.0-pro``.
    """
    _enforce_api_key(request)
    _enforce_rate_limit(request, limit=settings.rate_limit_normalize_per_minute, bucket="normalize")

    if not settings.c4norm_llm_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Visión no disponible: configura C4NORM_LLM_API_KEY y C4NORM_VISION_MODEL.",
        )

    # Nivel C4: campo explícito > prompt > 2 (por defecto)
    level = payload.c4_level or extract_level_from_prompt(payload.prompt)

    # Decodificar imagen
    try:
        image_bytes = base64.b64decode(payload.image_base64)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"image_base64 inválido: {exc}",
        ) from exc

    if len(image_bytes) > settings.max_xml_payload_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Imagen demasiado grande: {len(image_bytes)} bytes. Máximo: {settings.max_xml_payload_size}.",
        )

    # Visión: imagen → XML Draw.io crudo
    extractor = VisionExtractor(
        api_base=settings.c4norm_llm_api_base,
        api_key=settings.c4norm_llm_api_key,
        model=settings.c4norm_vision_model,
    )
    raw_xml = extractor.extract(image_bytes, prompt=payload.prompt, c4_level=level)

    # Normalizar: XML crudo → C4
    title_block = _build_title_block(payload.title_block)
    xml_c4, report = normalize(
        raw_xml,
        c4_level=level,
        classifier=payload.classifier,
        title_block=title_block,
    )

    compliance = None
    if payload.run_compliance_check:
        compliance = XMLLinter(settings).full_validation(xml_c4)

    return NormalizeResponse(
        xml_c4=xml_c4,
        report=NormalizeReportModel(**report.to_api_dict()),
        compliance=compliance,
    )


@app.get("/")
async def root() -> dict[str, object]:
    """Información del servicio."""
    return {
        "service": "drawio-automation-platform",
        "version": "0.1.0",
        "description": "Normalizador Draw.io -> C4",
        "docs": "/docs",
        "endpoints": [
            "POST /api/v1/diagram/normalize",
            "POST /api/v1/diagram/from-image",
            "GET /health",
            "GET /metrics",
        ],
    }
