# 📋 Documento de Diseño del Proyecto
## drawio-automation-platform

**Versión:** 1.0
**Fecha:** 30 de Mayo, 2026
**Estado:** v0.1.0 - Production Ready

---

## 1. Resumen Ejecutivo

### 1.1 Objetivo Principal
**Ordenar automáticamente diagramas de Draw.io a partir de su código XML para lograr un acabado visual apto para entregas profesionales**, eliminando la dependencia de intervención manual en el navegador y permitiendo integración en pipelines de automatización.

### 1.2 Problema Resuelto
Los algoritmos avanzados de layout de Draw.io (`mxHierarchicalLayout`, `mxFastOrganicLayout`, ELK) residen en el **DOM del navegador**, no en entornos CLI/backend. Esto imposibilita:
- Generación automática de diagramas en CI/CD
- Procesamiento por lotes de topologías de red
- Integración con orquestadores (n8n, Airflow)
- Validación de compliance corporativo pre-render

### 1.3 Solución Implementada
Microservicio completo que combina:
- **API REST (FastAPI)** para ingesta y validación temprana
- **Cola asíncrona (ARQ + Redis)** para desacople de cargas pesadas
- **Worker headless (Chromium + Xvfb)** para renderizado fiel
- **Sistema de fallback inteligente** con degradación graceful
- **Validación de compliance** (colores, stencils, licencias)

### 1.4 Diferenciadores Clave
| Característica | Soluciones Existentes | drawio-automation-platform |
|----------------|----------------------|---------------------------|
| Renderizado fiel | ❌ Solo CLI básica | ✅ Headless con Xvfb |
| Validación corporativa | ❌ Ninguna | ✅ lxml + políticas |
| Colas asíncronas | ❌ Single-threaded | ✅ ARQ + Redis |
| Stencils empresariales | ⚠️ Manuales | ✅ Auto-detección + caché |
| Fallback operativo | ❌ Crash total | ✅ Degradación graceful |
| Webhooks | ❌ No | ✅ Callbacks HTTP |
| Licenciamiento transparente | ⚠️ Opaco | ✅ AGPL-3.0 + NOTICE |

---

## 2. Arquitectura Técnica

### 2.1 Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────┐
│                         CLIENTES                            │
│  n8n / Airflow / Custom Apps / CI/CD Pipelines              │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ POST /api/v1/diagram/generate
                              │ { xml_payload, webhook_url }
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    FASTAPI REST API                         │
│  • Validación XML (lxml + XPath)                           │
│  • Compliance check (colores, stencils, licencias)         │
│  • Encolado ARQ (Redis)                                    │
│  • Retorno inmediato: { task_id, status: "queued" }        │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ enqueue_job("render_drawio")
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       REDIS QUEUE                           │
│  • Message broker                                          │
│  • Job state tracking                                      │
│  • Retry coordination                                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ consume job
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    ARQ WORKER                               │
│  1. StencilsLoader:                                        │
│     • Detección automática (regex)                         │
│     • Resolución con caché/descarga/placeholder            │
│     • Inyección <mxLibrary> en XML                         │
│  2. Renderizado headless:                                  │
│     • xvfb-run /opt/drawio/drawio                          │
│     • --libraries "aws4;azure;c4"                          │
│     • Retry inteligente (max 3, backoff)                   │
│  3. Post-procesamiento:                                    │
│     • Upload S3/MinIO (boto3)                              │
│     • Webhook callback (httpx)                             │
│     • FallbackReport → compliance JSON                     │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Stack Tecnológico

| Capa | Tecnología | Versión | Propósito |
|------|-----------|---------|-----------|
| **API** | FastAPI | 0.111.0 | REST endpoints, validación, OpenAPI docs |
| **Validación** | Pydantic v2 + lxml | 2.7.1 / 5.2.1 | Schemas + XML parsing con XPath |
| **Colas** | ARQ + Redis | 0.25.0 / 7.2 | Async task queue |
| **Storage** | boto3 | 1.34.101 | S3/MinIO upload |
| **HTTP Client** | httpx | 0.27.0 | Webhooks async |
| **Renderizado** | Draw.io Desktop | 24.4.8 | Binario headless (Chromium) |
| **Virtual Framebuffer** | Xvfb | Ubuntu 24.04 | Simulación de display |
| **Orquestación** | Docker Compose | 3.8 | Stack completo local |
| **CI/CD** | GitHub Actions | - | Build, test, release |

### 2.3 Estructura de Directorios

```
drawio-automation-platform/
├── api/                          # FastAPI REST API
│   ├── main.py                   # Endpoints + lifespan
│   ├── config.py                 # Pydantic Settings
│   ├── schemas.py                # Request/Response models
│   └── linting.py                # XMLLinter (lxml + XPath)
├── worker/                       # ARQ Worker
│   ├── tasks.py                  # render_drawio() + retry
│   ├── stencils_loader.py        # StencilsLoader + fallback
│   ├── models.py                 # FallbackReport, enums
│   ├── s3_uploader.py            # boto3 async wrapper
│   └── webhooks.py               # Callback dispatcher
├── scripts/                      # Automatización
│   ├── fetch_stencils.py         # Descarga + caché stencils
│   ├── verify_licenses.py        # Auditoría licencias
│   └── upstream_sync.sh          # Sync con fork upstream
├── stencils/
│   ├── manifest.json             # Metadata de 8 stencils
│   └── downloaded/               # Caché local (gitignored)
├── docker/
│   ├── Dockerfile.api            # FROM python:3.11-slim
│   ├── Dockerfile.worker         # FROM rlespinasse/drawio-desktop-headless
│   ├── docker-compose.yml        # Stack completo
│   └── worker-entrypoint.sh      # Bootstrap con verificaciones
├── tests/                        # pytest (57 tests)
├── .github/workflows/            # CI/CD (4 workflows)
├── NOTICE                        # Atribuciones obligatorias
├── FORK.md                       # Declaración de fork
├── THIRD_PARTY_LICENSES.md       # Auditoría de licencias
├── LICENSE                       # AGPL-3.0
└── pyproject.toml                # Configuración de proyecto
```

---

## 3. Componentes Críticos

### 3.1 Sistema de Validación Corporativa (`api/linting.py`)

**Funcionalidad:**
```python
class XMLLinter:
    def full_validation(xml_string) -> dict:
        # 1. validate_xml_wellformed (lxml)
        # 2. extract_colors (regex sobre fillColor/strokeColor/fontColor)
        # 3. validate_colors vs ALLOWED_COLORS
        # 4. detect_stencils (regex sobre shape=mxgraph.{stencil})
        # 5. validate_stencils vs ALLOWED_STENCILS
        # 6. requires_archimate_license
```

**Salida:**
```json
{
  "xml_valid": true,
  "colors_valid": true,
  "stencils_allowed": true,
  "detected_colors": ["#1e1e1e", "#ffffff"],
  "detected_stencils": ["aws4", "azure"],
  "archimate_license_required": false,
  "violations": [],
  "warnings": ["High color diversity: 12 unique colors"]
}
```

### 3.2 Sistema de Fallback Operativo (`worker/stencils_loader.py`)

**Matriz de Decisión:**

| Categoría | ¿Reintentable? | Acción | Estado Final |
|-----------|----------------|--------|--------------|
| `INVALID_XML` | ❌ | Abortar | `error` |
| `POLICY_VIOLATION` | ❌ | Bloquear antes de render | `blocked` |
| `LICENSE_MISSING` | ❌ | Bloquear antes de render | `blocked` |
| `STENCIL_FORBIDDEN` | ❌ | Bloquear antes de render | `blocked` |
| `NETWORK_TIMEOUT` | ✅ | Retry con backoff | `success` / `retry_exhausted` |
| `CHROMIUM_CRASH` | ✅ | Retry con backoff | `success` / `retry_exhausted` |
| `STENCIL_UNAVAILABLE` | ❌ | Degradar a placeholder | `degraded` |
| `OFFLINE_FALLBACK` | ❌ | Degradar a placeholder | `degraded` |

**Flujo de Resolución:**
```
resolve_stencil(name):
  1. ¿Prohibido por política? → BLOCK
  2. ¿Requiere licencia sin licencia? → BLOCK
  3. ¿En caché local? → usar (source="cache")
  4. ¿Modo offline? → placeholder (source="placeholder")
  5. ¿Built-in? → usar (source="built-in")
  6. Descargar con backoff (3 intentos, timeout 30s)
  7. Si falla → placeholder (source="placeholder")
```

### 3.3 Stencils Empresariales Soportados

| Stencil | Tipo | Licencia | Uso Comercial | Notas |
|---------|------|----------|---------------|-------|
| **AWS (aws4)** | built-in | AWS Terms | ✅ | Iconos oficiales de arquitectura |
| **GCP (gcp2)** | built-in | Google Cloud ToS | ✅ | Servicios Google Cloud |
| **Azure** | built-in | MIT-like | ✅ | Servicios Microsoft Azure |
| **ArchiMate 3.2** | built-in | **COMERCIAL** | 🔴 Requiere licencia | `ARCHIMATE_LICENSE_KEY` obligatorio |
| **C4 Model** | built-in | CC-BY-4.0 | ✅ | Simon Brown's C4 notation |
| **Cisco** | built-in | Terms of Use | ⚠️ No alterar | Iconos de red oficiales |
| **OCI** | downloadable | UPL-1.0 | ✅ | Oracle Cloud Infrastructure |
| **LeanIX** | unavailable | Propietario | ❌ | Solo en SaaS de SAP |

### 3.4 Inyección de Librerías (`<mxLibrary>`)

**Entrada:**
```xml
<mxfile>
  <diagram>
    <mxGraphModel>
      <mxCell style="shape=mxgraph.aws4.lambda" />
    </mxGraphModel>
  </diagram>
</mxfile>
```

**Procesamiento:**
1. Detección automática: regex `shape=mxgraph.aws4\.`
2. Construcción parámetro: `--libraries "aws4"`
3. Enriquecimiento XML:
```xml
<mxfile>
  <mxLibrary name="aws4" url="https://jgraph.github.io/drawio-libs/libs/aws4.xml"/>
  <diagram>...</diagram>
</mxfile>
```

---

## 4. Compliance y Licenciamiento

### 4.1 Licencia del Proyecto
- **AGPL-3.0** (compatible con el ecosistema Draw.io)
- Fork transparente de `rlespinasse/drawio-desktop-headless` (MIT)
- Archivo `NOTICE` con atribuciones completas
- Política upstream-first para contribuciones

### 4.2 Atribuciones Obligatorias (NOTICE)
```
Draw.io Automation Platform
Copyright 2026 [Tu Organización]

This product includes software developed by:
- JGraph Ltd (Draw.io) - Apache 2.0
- rlespinasse (drawio-desktop-headless) - MIT
- The Open Group (ArchiMate) - Commercial License Required
- Simon Brown (C4 Model) - Creative Commons BY 4.0
- Cisco Systems (Network Icons) - Terms of Use
- Oracle (OCI Icons) - UPL-1.0
- Google (GCP Icons) - Apache 2.0
- Microsoft (Azure Icons) - MIT-like
- Amazon (AWS Icons) - AWS Terms of Use
```

### 4.3 Auditoría de Licencias (`scripts/verify_licenses.py`)
- Escanea `stencils/manifest.json`
- Detecta incompatibilidades con AGPL-3.0
- Genera `THIRD_PARTY_LICENSES.md` automáticamente
- Falla CI si ArchiMate usado sin licencia válida

---

## 5. Limitaciones Conocidas

| Limitación | Impacto | Workaround |
|------------|---------|------------|
| Python 3.11 requerido | lxml no compila en 3.14 | Usar `py -3.11 -m venv .venv` |
| ArchiMate requiere licencia comercial | No se puede usar sin key | `ARCHIMATE_LICENSE_KEY` en `.env` |
| LeanIX no tiene stencil público | No disponible | Usar stencils alternativos de EAM |
| Consumo RAM alto (1.2GB worker) | Límites en contenedores | `WORKER_MAX_JOBS=3` para evitar OOM |
| Chromium headless frágil | Crashes aleatorios | Retry con backoff (3 intentos) |
| Sin soporte multi-página | Solo primera página | Dividir en múltiples requests |

---

## 6. Roadmap Futuro

> El roadmap detallado, con fases, cronograma y criterios de aceptación, vive en
> [ROADMAP.md](ROADMAP.md). Resumen:

### v0.2.0 - Mejoras de Producción (Q3 2026)
- [ ] Autenticación API (JWT + API Key)
- [ ] Rate limiting (fastapi-limiter)
- [ ] Métricas Prometheus (`/metrics` endpoint)
- [ ] Logging estructurado JSON (ELK/Splunk)
- [ ] Helm chart para Kubernetes

### v0.3.0 - Expansión de Stencils (Q4 2026)
- [ ] Kubernetes icons (oficiales)
- [ ] Terraform providers
- [ ] Azure DevOps
- [ ] SAP ERP components
- [ ] Custom stencil loader (desde URL)

### v1.0.0 - Estabilidad y Performance (Q1 2027)
- [ ] Soporte multi-página
- [ ] PDF export con capas editables
- [ ] Layout automático programático (ELK integration)
- [ ] Batch processing (100+ diagramas)
- [ ] SBOM generation (supply chain security)

---

## 7. Métricas del Proyecto

```
📊 Codebase Stats:
  - Total files: 46
  - Python code: ~2,000 lines
  - Test coverage: 55%
  - Tests: 57/57 passing ✅

🐳 Docker Images:
  - API: ~150 MB (python:3.11-slim)
  - Worker: ~1.2 GB (rlespinasse base)
  - Redis: ~30 MB (7.2-alpine)

⚡ Performance:
  - API response time: <100ms
  - Render time (simple): 5-10s
  - Render time (complex): 15-30s
  - Concurrent jobs: 3 (configurable)

🔐 Security:
  - Non-root containers ✅
  - No hardcoded secrets ✅
  - License compliance ✅
  - CORS configurable ✅
```

---

## Nota de validación contra el código (29-May-2026)

Al contrastar este diseño con el código real del repositorio, varios ítems
listados como "Roadmap v0.2.0 futuro" **ya están implementados** en `main`:

- **Rate limiting** → implementado en `api/main.py` (`_enforce_rate_limit`, ventana fija por IP/endpoint).
- **API Key auth** → implementado en `api/main.py` (`_enforce_api_key`, Bearer token). JWT aún no.
- **Endpoint `/metrics` Prometheus** → implementado en `api/main.py` (`_build_prometheus_metrics_text`).

Conviene actualizar el roadmap para reflejar este estado real (ver
[ROADMAP.md](ROADMAP.md)).
