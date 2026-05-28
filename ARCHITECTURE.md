# Architecture Document

## drawio-automation-platform

---

## System Overview

drawio-automation-platform is a multi-service system for rendering Draw.io diagrams
asynchronously with corporate compliance validation.

```
                    ┌─────────────┐
                    │   Client    │
                    └──────┬──────┘
                           │ HTTP POST /api/v1/diagram/generate
                           ▼
                    ┌─────────────┐
                    │  FastAPI     │ (api/)
                    │  - Validate  │
                    │  - Enqueue   │
                    └──────┬──────┘
                           │ ARQ enqueue
                           ▼
                    ┌─────────────┐
                    │   Redis      │ (7.2)
                    │   - Queue    │
                    │   - Results  │
                    └──────┬──────┘
                           │ ARQ dequeue
                           ▼
                    ┌─────────────┐
                    │   Worker     │ (worker/)
                    │  - Stencils  │
                    │  - Render    │
                    │  - Upload    │
                    │  - Webhook   │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌─────────┐  ┌─────────┐  ┌─────────┐
        │  Draw.io │  │ S3/MinIO│  │ Webhook │
        │  (Electron)│ │         │  │  URL    │
        └─────────┘  └─────────┘  └─────────┘
```

---

## Component Details

### API Service (`api/`)

**Framework:** FastAPI 0.111.0 on Python 3.11  
**Role:** HTTP interface, validation gateway, task enqueuer

**Responsibilities:**
- Accepts diagram generation requests via REST API
- Validates XML compliance (colors, stencils, licenses) using lxml
- Rejects non-compliant requests before enqueuing
- Enqueues compliant requests into ARQ (Redis) task queue
- Provides task status endpoint

**Key Design Decisions:**
- **No BackgroundTasks for rendering.** FastAPI's BackgroundTasks are
  not suitable for long-running, resource-intensive tasks. ARQ with Redis
  provides persistence, retry, and observability.
- **Rejected tasks still return 202.** The HTTP status indicates the request
  was accepted and processed. The task status field (`rejected`) communicates
  compliance decisions.
- **Validation happens at the API layer**, not in the worker. This prevents
  invalid tasks from consuming worker resources.

### Worker Service (`worker/`)

**Framework:** ARQ 0.25.0 on Python 3.11  
**Role:** Async task processor for diagram rendering

**Task Flow:**
1. Dequeue job from Redis
2. Resolve stencils (cached, download, fallback, or block)
3. Execute drawio CLI with Chromium flags
4. Upload rendered output to S3/MinIO
5. Send webhook notification
6. Store result in Redis

**Retry Strategy:**
- **Transient failures** (TIMEOUT, OOM, NODE_CRASH): Retry up to 2 times with
  exponential backoff
- **Non-transient failures** (INVALID_XML, POLICY_VIOLATION, LICENSE_MISSING):
  Never retry — fail immediately
- ARQ's built-in `retry_jobs` is set to **False**; retry logic is handled
  manually for granular control

**Stencil Resolution Matrix:**

| Condition | Action |
|-----------|--------|
| License OK + Cached | Use cached stencil |
| License OK + Not cached | Download from source (with retry) |
| License OK + Offline + Not cached | Placeholder (basic shapes) |
| License BLOCKED (ArchiMate, no key) | BLOCK rendering entirely |
| License BLOCKED (policy violation) | BLOCK rendering entirely |
| Stencil unavailable (leanix) | BLOCK rendering entirely |

### Redis

**Role:** Task queue backend and result store

- **Queue persistence:** Jobs survive Redis restarts (AOF enabled)
- **Result TTL:** Configurable via `ARQ_EXPIRES` (default 1 hour)
- **Memory limit:** 256MB with allkeys-lru eviction policy

### S3/MinIO

**Role:** Persistent storage for rendered diagrams

- Supports both AWS S3 and MinIO (self-hosted)
- Presigned URLs for time-limited access (default 1 hour)
- Objects stored as private by default

---

## Data Flow

### Diagram Generation Request

```
1. Client POSTs XML to /api/v1/diagram/generate
2. API validates XML compliance (lxml)
3. If BLOCKED → return 202 with status=rejected
4. If compliant → enqueue ARQ job → return 202 with task_id
5. Worker dequeues job
6. Worker resolves stencils (cached, download, or fallback)
7. Worker executes drawio CLI with --export
8. Worker uploads output to S3/MinIO
9. Worker sends webhook notification
10. Worker stores result in Redis
11. Client polls GET /api/v1/diagram/status/{task_id}
```

### Task Status Query

```
1. Client GETs /api/v1/diagram/status/{task_id}
2. API queries ARQ job result from Redis
3. If not found → return status=queued
4. If completed → return status=completed with S3 URL
5. If failed → return status=failed with error details
```

---

## Compliance Architecture

### Validation Pipeline

```
XML Content
    ↓
1. XML Well-Formedness Check (lxml parser)
    ↓
2. Color Extraction & Validation (regex + ALLOWED_COLORS)
    ↓
3. Stencil Detection & Validation (shape patterns + ALLOWED_STENCILS)
    ↓
4. ArchiMate License Check (ARCHIMATE_LICENSE_KEY)
    ↓
ComplianceCheck Result (COMPLIANT | WARNING | BLOCKED)
```

### Color Validation

- Scans `fillColor`, `strokeColor`, `fontColor`, and other attributes
- Compares against `ALLOWED_COLORS` list (hex values without `#`)
- Default colors (`none`, `default`, `transparent`, `#ffffff`, `#000000`) are always allowed
- Empty `ALLOWED_COLORS` disables validation (all colors allowed)

### Stencil Validation

- Detects stencil usage via shape name patterns in mxCell style attributes
- Validates against `ALLOWED_STENCILS` list
- LeanIX is permanently marked as `unavailable` — always blocked

---

## Container Architecture

### API Container

- **Base image:** python:3.11-slim-bookworm
- **User:** appuser (non-root)
- **Workers:** 4 uvicorn workers
- **Memory limit:** 512MB
- **Health check:** HTTP GET /health

### Worker Container

- **Base image:** rlespinasse/drawio-desktop-headless:latest
- **User:** drawuser (from base image)
- **Includes:** Draw.io Desktop, Xvfb, Chromium
- **Memory limit:** 2GB (rendering is memory-intensive)
- **Health check:** Redis PING

---

## Directory Structure

```
drawio-automation-platform/
├── api/                  # FastAPI REST API
│   ├── config.py         # Pydantic Settings
│   ├── linting.py        # XML validation
│   ├── main.py           # API endpoints
│   ├── schemas.py        # Pydantic models
│   └── requirements.txt
├── worker/               # ARQ worker
│   ├── models.py         # Data models
│   ├── stencils_loader.py # Stencil resolution
│   ├── tasks.py          # render_drawio task
│   ├── s3_uploader.py    # S3/MinIO upload
│   ├── webhooks.py       # Webhook notifier
│   └── requirements.txt
├── docker/               # Docker configuration
│   ├── Dockerfile.api
│   ├── Dockerfile.worker
│   ├── worker-entrypoint.sh
│   └── docker-compose.yml
├── stencils/             # Stencil manifest and cache
│   ├── manifest.json
│   └── downloaded/
├── scripts/              # Utility scripts
│   ├── fetch_stencils.py
│   ├── verify_licenses.py
│   ├── upstream_sync.sh
│   └── init_fork.sh
├── tests/                # Test suite
├── .github/workflows/    # CI/CD pipelines
├── LICENSE               # AGPL-3.0
├── NOTICE                # Third-party attributions
└── pyproject.toml        # Project configuration
```

---

## Security Considerations

- **Non-root users** in both containers
- **No network access** for XML parser (`no_network=True`)
- **XML entity resolution disabled** to prevent XXE attacks
- **tmpfs** for temporary file storage (in-memory, cleared on restart)
- **Private S3 objects** with presigned URLs for controlled access
- **No hardcoded credentials** — all via environment variables
- **API key support** for endpoint protection (optional, via `API_KEY`)

---

## Observability

- **Structured JSON logging** with configurable log levels
- **Health check endpoints** for both API and Worker
- **Request ID tracking** via `X-Request-ID` header
- **Webhook notifications** with comprehensive task reports
- **Redis monitoring** via health checks and connection pooling metrics