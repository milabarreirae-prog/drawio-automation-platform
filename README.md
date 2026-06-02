# c4norm — Normalizador Draw.io → C4

Convierte XML crudo de Draw.io (normalmente generado por IA, en formato libre) en
**diagramas C4 conformes a estándar**: tipados, con layout limpio y un cajetín
ISO 7200, listos para publicar en Confluence (que los renderiza con su propio
plugin de Draw.io).

> **Diseño autoritativo:** [`docs/C4_NORMALIZER_DESIGN.md`](docs/C4_NORMALIZER_DESIGN.md) ·
> **Arquitectura:** [`ARCHITECTURE.md`](ARCHITECTURE.md) ·
> **Hoja de ruta:** [`docs/ROADMAP.md`](docs/ROADMAP.md)

## Pipeline

```
XML crudo (mxfile | mxGraphModel)
  → parse + saneo (mojibake, formato)           c4norm/parse.py
  → modelo lógico (+ repara aristas huérfanas)  c4norm/model.py
  → clasifica a C4 (heurístico | LLM)           c4norm/classify.py
  → ancla nodos flotantes                       c4norm/ground.py
  → layout (ELK real | fallback Python)         c4norm/layout/
  → emite C4 + hoja ISO 7200                    c4norm/emit.py, c4norm/sheet.py
  → XML C4 listo para Confluence
```

## Requisitos e instalación

- **Python ≥ 3.11**
- **Node.js** (opcional) para el layout con ELK real vía `elkjs`

```bash
python -m pip install -e ".[dev]"
npm install --prefix c4norm/layout   # opcional: habilita ElkLayout (ELK real)
```

Si Node/`elkjs` no está disponible, el normalizador usa el layout en Python puro
(`LayeredLayout`).

## Uso

```bash
python -m c4norm <entrada.drawio.xml> --level 2 -o <salida.drawio.xml>
```

| Opción | Por defecto | Descripción |
|--------|-------------|-------------|
| `--level {1,2,3}` | `2` | Nivel C4 objetivo |
| `--classifier {heuristic,llm,auto}` | `heuristic` | Estrategia de clasificación a C4 |
| `-o, --output` | stdout | Archivo de salida |

**Cajetín ISO 7200:** `--project`, `--title`, `--type` (As-Is / To-Be / …),
`--arch`, `--drawn-by`, `--rev`, `--date`.

```bash
python -m c4norm crudo.drawio.xml --level 2 \
  --project "BFCL" --title "Arquitectura As-Is" --type As-Is \
  --arch "Camila" --rev A -o as-is-c4.drawio.xml
```

El comando escribe el XML C4 en la salida e imprime un resumen en `stderr`
(nodos, aristas, escala, hoja, motor de layout).

## Uso como servicio (API)

Además del CLI hay una API FastAPI **síncrona** (docs interactivas en `/docs`):

```bash
uvicorn api.main:app --reload     # http://localhost:8000
```

| Endpoint | Qué hace |
|----------|----------|
| `POST /api/v1/diagram/normalize` | Normaliza XML crudo → C4. Cuerpo: `xml_content`, `c4_level`, `classifier`, `title_block`, `run_compliance_check` |
| `GET /health` | Estado + motor de layout disponible (`elk` / `layered`) |
| `GET /metrics` | Métricas Prometheus |

```bash
curl -s http://localhost:8000/api/v1/diagram/normalize \
  -H "Content-Type: application/json" \
  -d '{"xml_content":"<mxGraphModel>...</mxGraphModel>","c4_level":2}'
# -> { "xml_c4": "...", "report": { ... }, "compliance": null }
```

Auth opcional por API key (`API_KEY` → cabecera `Authorization: Bearer <key>`) y rate limiting por IP.

## Estructura

| Ruta | Contenido |
|------|-----------|
| `c4norm/` | Motor: parse, modelo, clasificación, anclado, dimensionado, emisión |
| `c4norm/layout/` | Layout intercambiable: `ElkLayout` (ELK vía Node) · `LayeredLayout` (Python) |
| `api/` | API FastAPI síncrona (`/normalize`), compliance (lxml) y schemas Pydantic |
| `docs/` | Diseño, arquitectura y hoja de ruta |
| `tests/` | Pruebas pytest del motor |

## Pruebas

```bash
pytest
```

## Docker

La imagen incluye Python + Node.js (para el layout ELK real):

```bash
docker compose up --build          # API en http://localhost:8000
# o, sin compose:
docker build -t drawio-c4-normalizer .
docker run --rm -p 8000:8000 drawio-c4-normalizer
```

## Licencia

Ver [`LICENSE`](LICENSE) y [`NOTICE`](NOTICE).
