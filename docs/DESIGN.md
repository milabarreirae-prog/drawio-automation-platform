# Documento de Diseño — drawio-automation-platform

**Versión:** 2.0 · **Estado:** normalizador C4 (motor funcional + API + contenedor)

> Diseño **autoritativo del motor**: [C4_NORMALIZER_DESIGN.md](C4_NORMALIZER_DESIGN.md).
> Vista de arquitectura: [../ARCHITECTURE.md](../ARCHITECTURE.md). Estado/plan: [ROADMAP.md](ROADMAP.md).

## 1. Objetivo

Tomar **XML crudo de Draw.io** (normalmente generado por IA, en formato libre y
desordenado) y producir **XML Draw.io conforme al estándar C4**, con layout limpio y
un cajetín ISO 7200, listo para **publicar en Confluence** (que lo renderiza con su
propio plugin de draw.io). El entregable es **XML → XML**: no se rasteriza. El usuario
**declara el nivel C4** (1, 2 o 3).

## 2. Qué cambió respecto a v0.1.0

El proyecto nació (v0.1.0) como una **plataforma de rendering headless**: una API que
encolaba trabajos y un worker (Chromium/Xvfb + Draw.io Desktop) que rasterizaba a
imagen/PDF, con S3, webhooks y resolución de stencils. Al refinar el requerimiento real
(29-May-2026) el objetivo pasó a **normalizar a C4 (XML→XML)**, y esa capa de rendering
quedó de sobra:

| Componente v0.1.0 | Hoy |
|---|---|
| Worker headless (Chromium/Xvfb) | ❌ Eliminado (Confluence renderiza) |
| Cola ARQ + Redis | ❌ Eliminado (el trabajo es síncrono, de ms-segundos) |
| S3/MinIO + webhooks | ❌ Eliminado |
| Resolución de stencils + `<mxLibrary>` | ❌ Eliminado |
| Parsing lxml, schemas Pydantic, patrón FastAPI, validación | ✅ Reutilizado |

## 3. Arquitectura actual

```
   CLI: python -m c4norm            API: POST /api/v1/diagram/normalize
            │                                       │
            └───────────────────┬───────────────────┘
                                ▼
        c4norm.normalize(xml, c4_level, classifier, title_block)
                                │
 parse → modelo lógico → clasificar C4 → anclar → layout (ELK|fallback) → emitir C4 + cajetín
                                │
                          XML C4  (+ reporte)
```

- **Motor (`c4norm/`)** — pipeline síncrono; diseño detallado en C4_NORMALIZER_DESIGN.md.
- **API (`api/`)** — FastAPI síncrona: `POST /api/v1/diagram/normalize`, `GET /health`,
  `GET /metrics`. Auth opcional (API key) + rate limiting. Compliance opcional.
- **Layout** — `ElkLayout` (ELK real vía elkjs/Node) con fallback `LayeredLayout` (Python puro).
- **Contenedor** — imagen con Python + Node.js (elkjs) que sirve la API con uvicorn.

## 4. Validación / compliance

`api/linting.py` (lxml) valida XML bien formado, paleta de colores (`ALLOWED_COLORS`),
stencils permitidos (`ALLOWED_STENCILS`) y licencia ArchiMate. Es **opcional y ortogonal**
a la normalización: se activa con `run_compliance_check` en la petición.

## 5. Pruebas

`pytest` (`tests/test_c4norm.py`, `tests/test_api.py`, `tests/test_linting.py`). Para
ejercitar ELK real: `npm install --prefix c4norm/layout` (si no, usa el fallback Python).
No hay CI en GitHub: se valida en local.

## 6. Licencia

MIT (ver [../LICENSE](../LICENSE) y [../NOTICE](../NOTICE)). El proyecto deriva del fork
MIT `rlespinasse/docker-drawio-desktop-headless`, cuya capa de runtime fue retirada.
