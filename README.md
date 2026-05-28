# drawio-automation-platform

Enterprise Draw.io automation platform with REST API, async rendering, and corporate compliance validation.

> **Fork of** [rlespinasse/drawio-desktop-headless](https://github.com/rlespinasse/drawio-desktop-headless) — See [FORK.md](FORK.md) for details.

---

## Overview

This platform extends the excellent headless Draw.io Docker image with:

- **REST API** (FastAPI) for programmatic diagram generation
- **Async Task Queue** (ARQ + Redis) for non-blocking rendering
- **Corporate Compliance** validation of colors, stencils, and licenses
- **Enterprise Stencil Support** (AWS, GCP, Azure, ArchiMate, C4, Cisco, OCI)
- **S3/MinIO Storage** integration for export delivery
- **Webhook Callbacks** for async task notifications
- **Multi-tenant Architecture** with isolated workers and resource limits

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local development)

### Run with Docker Compose

```bash
# Clone the repository
git clone https://github.com/YOUR_ORG/drawio-automation-platform.git
cd drawio-automation-platform

# Copy environment configuration
cp .env.example .env

# Start services (Redis + API + Worker)
docker compose -f docker/docker-compose.yml up -d

# Optional: Start MinIO for local S3 storage
docker compose -f docker/docker-compose.yml --profile dev up -d minio

# Check health
curl http://localhost:8000/health
```

### Generate a Diagram

```bash
curl -X POST http://localhost:8000/api/v1/diagram/generate \
  -H "Content-Type: application/json" \
  -d '{
    "xml_content": "<mxGraphModel><root><mxCell id=\"0\"/><mxCell id=\"1\" parent=\"0\"/><mxCell id=\"2\" value=\"Hello\" style=\"rounded=1;fillColor=#4A90D9;strokeColor=#333333;\" vertex=\"1\" parent=\"1\"><mxGeometry x=\"200\" y=\"150\" width=\"120\" height=\"60\" as=\"geometry\"/></mxCell></root></mxGraphModel>",
    "export_format": "svg",
    "webhook_url": "https://your-callback.example.com/hook"
  }'

# Check task status
curl http://localhost:8000/api/v1/diagram/status/<task_id>
```

---

## Architecture

```
Client → FastAPI → Redis/ARQ → Worker → Draw.io CLI → S3/MinIO → Webhook
         │                        │
         └── Compliance ──────────┘
         (lxml validation)
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design documentation.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check with Redis status |
| `GET` | `/` | API info and docs links |
| `POST` | `/api/v1/diagram/generate` | Submit diagram for rendering |
| `GET` | `/api/v1/diagram/status/{task_id}` | Check rendering task status |

Interactive API docs available at `/docs` (Swagger UI) and `/redoc`.

---

## Compliance Validation

The platform validates diagrams against corporate policies before rendering:

- **Color Palette**: Only allowed hex colors can be used (configured via `ALLOWED_COLORS`)
- **Stencil Libraries**: Only approved stencil sets are permitted (configured via `ALLOWED_STENCILS`)
- **License Requirements**: ArchiMate commercial use requires a license key (`ARCHIMATE_LICENSE_KEY`)
- **XML Integrity**: Malformed XML is rejected before reaching the renderer

Violations return status `rejected` with detailed compliance reports.

---

## Stencil Libraries

| Stencil | Vendor | License | Commercial Use |
|---------|--------|---------|----------------|
| AWS (aws4) | Amazon | Proprietary | With attribution |
| GCP (gcp2) | Google | CC BY 4.0 | With attribution |
| Azure (azure2) | Microsoft | Proprietary | With attribution |
| ArchiMate 3 (archimate3) | The Open Group | Proprietary | License required |
| C4 Model (c4) | Simon Brown | CC BY 4.0 | With attribution |
| Cisco (cisco19) | Cisco | Proprietary | With attribution |
| OCI (oci) | Oracle | Proprietary | With attribution |
| LeanIX | LeanIX/SAP | Proprietary | Unavailable by default |

See [stencils/manifest.json](stencils/manifest.json) for complete metadata and download sources.

---

## Development

### Local Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .\.venv\Scripts\activate on Windows

# Install dependencies
pip install -e ".[dev]"
pip install -r api/requirements.txt -r worker/requirements.txt

# Run tests
pytest tests/ -v

# Run linter
ruff check api/ worker/ tests/ scripts/

# Start API locally (requires Redis)
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### Running Workers Locally

```bash
# Start ARQ worker
arq worker.tasks.WorkerSettings --workers 1
```

---

## Docker Build

```bash
# Build API image
docker build -f docker/Dockerfile.api -t drawio-api:latest .

# Build Worker image
docker build -f docker/Dockerfile.worker -t drawio-worker:latest .
```

---

## Configuration

All configuration is via environment variables. See [.env.example](.env.example) for a complete reference.

Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `redis` | Redis hostname |
| `S3_BUCKET_NAME` | `drawio-exports` | S3/MinIO bucket |
| `ALLOWED_STENCILS` | `aws4,gcp2,...` | Allowed stencil IDs |
| `ALLOWED_COLORS` | (empty) | Allowed hex colors (empty = all allowed) |
| `ARCHIMATE_LICENSE_KEY` | (empty) | ArchiMate license for commercial use |
| `WORKER_MAX_JOBS` | `3` | Max concurrent rendering jobs |

---

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

- Original upstream code: MIT License (rlespinasse/drawio-desktop-headless)
- This fork additions: AGPL-3.0
- See [LICENSE](LICENSE) for full text
- See [NOTICE](NOTICE) for third-party attributions
- See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) for stencil library licenses

---

## Acknowledgments

This project stands on the shoulders of:

- **JGraph Ltd** — creators of Draw.io / diagrams.net
- **Romain Lespinasse** — maintainer of rlespinasse/drawio-desktop-headless
- **The Open Group** — ArchiMate specification
- **Simon Brown** — C4 Model for software architecture
- **All stencil vendors** — AWS, Google, Microsoft, Cisco, Oracle

See [NOTICE](NOTICE) for complete attributions.