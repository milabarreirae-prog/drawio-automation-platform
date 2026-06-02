# Architecture

## Overview

The core of this project is a **Draw.io → C4 normalizer** (`c4norm/`): it takes raw
Draw.io XML (typically AI-generated, free-form) and produces standards-compliant
**C4** Draw.io XML — clean, laid out, and ready to publish in Confluence.

> The authoritative design lives in
> [docs/C4_NORMALIZER_DESIGN.md](docs/C4_NORMALIZER_DESIGN.md). See also
> [docs/DESIGN.md](docs/DESIGN.md) and [docs/ROADMAP.md](docs/ROADMAP.md).

The earlier **headless rendering platform** (async render worker, Redis/ARQ queue,
S3 upload, webhooks, stencil resolution, render Docker stack) was **removed** as it
does not serve the XML→C4 requirement: the normalizer outputs XML, and Confluence
renders it with its own Draw.io plugin.

## Pipeline (c4norm)

```
XML crudo (mxfile | mxGraphModel)
  → parse + sanear (mojibake, formato)        c4norm/parse.py
  → modelo lógico (+ reparar huérfanas)       c4norm/model.py
  → clasificar a C4 (heurístico | LLM)         c4norm/classify.py
  → anclar nodos flotantes                    c4norm/ground.py
  → layout (ELK real | fallback Python)       c4norm/layout/
  → emitir C4 + hoja ISO 7200 ajustada        c4norm/emit.py, c4norm/sheet.py
  → XML C4 para Confluence
```

CLI: `python -m c4norm <in.drawio.xml> --level {1|2|3} -o <out.xml>`.

## Main Components

### Normalizer core (`c4norm/`)
- `model.py` — modelo lógico + estándar C4 canónico (tipo → forma/color/etiqueta).
- `parse.py` — acepta `mxfile` y `mxGraphModel` pelado; sanea mojibake; reconstruye
  aristas huérfanas por proximidad.
- `classify.py` — interfaz `C4Classifier`: `HeuristicClassifier` (determinista) y
  `LLMClassifier` (OpenAI-compatible, provider-agnóstico). Modos: `heuristic` / `llm` /
  `auto` (LLM solo en nodos de baja confianza si hay clave; si no, heurístico puro).
  Lotes de hasta 20 nodos; el LLM nunca inventa — tipo inválido conserva el heurístico.
- `ground.py` — ancla nodos de infra flotantes en un boundary de conectividad.
- `sizing.py` — dimensiona cada caja a su texto.
- `layout/` — motor intercambiable: **`ElkLayout`** (ELK real vía `elkjs`/Node,
  ruteo ortogonal que esquiva cajas) y **`LayeredLayout`** (fallback Python puro).
- `sheet.py` — hoja ajustada al contenido (1:1) + cajetín ISO 7200.
- `emit.py` — serializa a XML C4 (`<object>` tipados + estilo canónico + waypoints).
  Devuelve `EmitResult`; soporta multi-hoja: si el diagrama desborda y hay ≥2 boundaries,
  genera una hoja por boundary + "Contexto" con sus propios cajetines ("Hoja N de M").

### API (`api/`)
API FastAPI **síncrona** que expone el normalizador:
- `POST /api/v1/diagram/normalize` — XML crudo + nivel C4 (+ cajetín opcional) →
  llama a `c4norm.normalize` y devuelve XML C4 + reporte; compliance opcional.
- `GET /health` (incluye el motor de layout disponible) y `GET /metrics` (Prometheus).
- Auth opcional por API key (Bearer) y rate limiting por IP.

`api/linting.py` aporta la validación de compliance opcional (lxml + políticas) y
`api/schemas.py` los modelos Pydantic. El trabajo es de ms-segundos: no hay cola ni
workers.

## Origen (fork)

El proyecto nació como fork del runtime headless de Draw.io
(`rlespinasse/docker-drawio-desktop-headless`). Esa capa de rendering y todos sus
restos (`src/`, `Dockerfile` raíz, pruebas Bats, workflows de drawio-desktop,
`THIRD_PARTY_LICENSES`, metadata `.github/`) se **eliminaron**; sólo se conservan
`LICENSE` y `NOTICE`. El repositorio ya no tiene automatización de GitHub.

## Validation

Pruebas Python (78 tests): `test_c4norm.py` (pipeline completo, ELK + fallback),
`test_api.py` (endpoint `/normalize`, auth, rate limit), `test_linting.py` (compliance),
`test_llm_classifier.py` (LLM con `chat` inyectado, sin red), `test_ground.py`
(anclado por tipo y casos límite), `test_multisheet.py` (descomposición por boundary).
Para ejercitar ELK real: `npm install --prefix c4norm/layout`; sin Node, usa el
fallback Python. No hay CI en GitHub: se valida en local.
