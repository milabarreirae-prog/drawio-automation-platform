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
  → clasificar a C4 (heurístico | LLM stub)   c4norm/classify.py
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
  `LLMClassifier` (stub pluggable, API tipo OpenAI, para corregir fuera de estándar).
- `ground.py` — ancla nodos de infra flotantes en un boundary de conectividad.
- `sizing.py` — dimensiona cada caja a su texto.
- `layout/` — motor intercambiable: **`ElkLayout`** (ELK real vía `elkjs`/Node,
  ruteo ortogonal que esquiva cajas) y **`LayeredLayout`** (fallback Python puro).
- `sheet.py` — hoja ajustada al contenido (1:1) + cajetín ISO 7200.
- `emit.py` — serializa a XML C4 (`<object>` tipados + estilo canónico + waypoints).

### Reusable API/compliance (`api/`)
`api/{config,linting,schemas}.py` aportan validación de compliance (lxml + políticas)
y schemas Pydantic reutilizables; `api/main.py` es el scaffold FastAPI (pendiente de
repurposing a un endpoint `/normalize`).

## Upstream fork base (sin tocar)

El repositorio sigue siendo un fork del runtime headless de Draw.io. Su base
(`src/`, `Dockerfile` raíz, pruebas Bats en `tests/*.bats`, workflows de
drawio-desktop, `NOTICE`/`THIRD_PARTY_LICENSES`) se conserva por sus atribuciones
legales; no es parte del normalizador C4 y puede retirarse aparte si se decide
desligar el proyecto del fork.

## Validation

Pruebas Python: `tests/test_linting.py`, `tests/test_api.py`, `tests/test_c4norm.py`
(motor ELK + fallback, parse, clasificación, hoja/cajetín). CI en
`.github/workflows/ci.yml` instala Node + `elkjs` para ejercitar ELK real.
