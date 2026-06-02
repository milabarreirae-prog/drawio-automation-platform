# Guía de usuario — c4norm

Cómo normalizar un Draw.io crudo a **C4 conforme a estándar**, por línea de comandos
o por API.

## 1. Instalación

Requisito: **Python ≥ 3.11**. Opcional: **Node.js** (para el layout ELK real).

```bash
python -m pip install -e ".[dev]"
npm install --prefix c4norm/layout    # opcional: habilita ELK real
```

Sin Node, el motor usa el layout en Python puro (`LayeredLayout`) automáticamente.

## 2. Quickstart (CLI)

```bash
python -m c4norm crudo.drawio.xml --level 2 -o salida.drawio.xml
```

Abre `salida.drawio.xml` en draw.io o publícalo en Confluence. El comando imprime un
resumen en `stderr` (nodos, aristas, escala, hoja, motor de layout).

## 3. CLI — referencia

```
python -m c4norm <entrada.drawio.xml> [opciones]
```

| Opción | Por defecto | Descripción |
|--------|-------------|-------------|
| `--level {1,2,3}` | `2` | Nivel C4 (1 sistemas · 2 contenedores · 3 componentes) |
| `--classifier {heuristic,llm,auto}` | `heuristic` | Estrategia de clasificación |
| `-o, --output RUTA` | stdout | Archivo de salida |
| `--project TEXTO` | `—` | Cajetín: proyecto |
| `--title TEXTO` | nombre del diagrama | Cajetín: título |
| `--type TEXTO` | — | Cajetín: As-Is / To-Be / … |
| `--drawn-by TEXTO` | `c4norm` | Cajetín: dibujó |
| `--arch TEXTO` | `—` | Cajetín: revisó / arquitecto |
| `--rev TEXTO` | `A` | Cajetín: revisión |
| `--date ISO` | hoy | Cajetín: fecha |

```bash
python -m c4norm crudo.drawio.xml --level 2 \
  --project "BFCL" --title "Arquitectura As-Is" --type As-Is \
  --arch "Camila" --rev A -o as-is-c4.drawio.xml
```

## 4. API

```bash
uvicorn api.main:app --reload      # http://localhost:8000  ·  docs en /docs
```

### POST /api/v1/diagram/normalize

| Campo | Tipo | Por defecto | Descripción |
|-------|------|-------------|-------------|
| `xml_content` | string | (requerido) | XML Draw.io crudo |
| `c4_level` | 1·2·3 | 2 | Nivel C4 |
| `classifier` | heuristic·llm·auto | heuristic | Clasificador |
| `title_block` | objeto | null | `project, title, doc_type, drawn_by, approved_by, date, revision` |
| `run_compliance_check` | bool | false | Corre el linter de compliance sobre la salida |

Respuesta:

```json
{
  "xml_c4": "<mxfile> … </mxfile>",
  "report": {
    "diagram_name": "Arquitectura N2", "c4_level": 2,
    "node_count": 6, "edge_count": 5, "inferred_edges": 0, "grounded_nodes": 0,
    "type_histogram": {"Person": 1, "Container": 4, "Database": 1},
    "low_confidence": [], "scale": "1:1", "overflow": false,
    "sheet": "A4", "orientation": "portrait", "engine": "ElkLayout",
    "sheets": 1, "cross_sheet_edges": 0
  },
  "compliance": null
}
```

```bash
curl -s http://localhost:8000/api/v1/diagram/normalize \
  -H "Content-Type: application/json" \
  -d '{"xml_content":"<mxGraphModel>...</mxGraphModel>","c4_level":2}'
```

Otros endpoints: `GET /health` (incluye `layout_engine`) y `GET /metrics` (Prometheus).

## 5. Docker

```bash
docker compose up --build       # API en http://localhost:8000
```

La imagen incluye Node.js + elkjs, así que el contenedor usa ELK real.

## 6. Configuración (variables de entorno)

| Variable | Por defecto | Para qué |
|----------|-------------|----------|
| `API_KEY` | (vacío) | Si se define, exige `Authorization: Bearer <key>` |
| `CORS_ORIGINS` | `*` | Orígenes permitidos |
| `RATE_LIMIT_NORMALIZE_PER_MINUTE` | 60 | Límite por IP |
| `MAX_XML_PAYLOAD_SIZE` | 10485760 | Tamaño máx. del XML (bytes) |
| `ALLOWED_STENCILS` / `ALLOWED_COLORS` | aws4,… / (vacío) | Política de compliance |
| `ARCHIMATE_LICENSE_KEY` | (vacío) | Habilita stencils ArchiMate en compliance |
| `C4NORM_LAYOUT` | auto | Forzar motor de layout: `elk` o `layered` |
| `C4NORM_NODE_BIN` | — | Ruta a Node si no está en el PATH |
| `C4NORM_LLM_API_BASE` | `https://api.openai.com/v1` | Endpoint OpenAI-compatible (ver §7) |
| `C4NORM_LLM_API_KEY` | (vacío) | Clave del LLM (requerida para `--classifier llm/auto`) |
| `C4NORM_LLM_MODEL` | `gpt-4o-mini` | Modelo del LLM |

## 7. Clasificador LLM

### Modos
| Modo | Comportamiento |
|------|----------------|
| `heuristic` | Determinista. Sin coste. Por defecto. |
| `llm` | Envía todos los nodos al LLM. Requiere `C4NORM_LLM_API_KEY`. |
| `auto` | Heurístico completo + LLM solo en nodos de **baja confianza** (sin `c4Type` explícito). Cae a `heuristic` si no hay clave. Recomendado para producción. |

El LLM **nunca inventa**: solo re-tipa nodos existentes; tipo inválido → conserva el heurístico.
Diagramas con más de 20 nodos se procesan en lotes automáticamente.

### Proveedores compatibles

Cualquier endpoint `/chat/completions` con soporte de `response_format: json_object`:

| Proveedor | `C4NORM_LLM_API_BASE` | Modelos |
|-----------|----------------------|---------|
| **Alibaba Cloud MaaS** _(conectado)_ | `https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1` | `qwen3.7-max`, `qwen3.6-plus`, `qwen3.6-flash`, `deepseek-v4-pro`, `deepseek-v4-flash`, `kimi-k2.6`, `glm-5.1` … |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o`, `gpt-4o-mini` |
| Azure OpenAI | `https://<resource>.openai.azure.com/openai/deployments/<deploy>` | modelo por deployment |

```bash
# Ejemplo — Alibaba MaaS con qwen3.7-max
export C4NORM_LLM_API_BASE=https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1
export C4NORM_LLM_API_KEY=<clave>
export C4NORM_LLM_MODEL=qwen3.7-max
python -m c4norm crudo.drawio.xml --level 2 --classifier auto -o salida.drawio.xml
```

## 8. Multi-hoja

Si un diagrama no cabe ni a la escala mínima **y** tiene ≥2 sitios (boundaries), la
salida se parte en **una hoja por sitio** (vista de deployment) + una hoja
"Contexto". Las aristas que cruzan hojas se cuentan en `report.cross_sheet_edges`
(no se dibujan: una vista no debe insinuar conexiones que no contiene).

## 9. Principio: el motor nunca inventa

c4norm preserva y eleva lo que existe; lo que falta lo marca, no lo fabrica. La
metadata epistémica (`Confianza: Baja`, `Estado CMDB: Pendiente`) se conserva en la
descripción del nodo/relación.

## 10. Problemas frecuentes

| Síntoma | Causa / solución |
|---------|------------------|
| `layout_engine: layered` en vez de `elk` | Falta Node/elkjs: `npm install --prefix c4norm/layout` o define `C4NORM_NODE_BIN`. |
| Acentos rotos (`PeticiÃ³n`) | Mojibake del round-trip de Confluence; c4norm lo sanea al parsear. |
| `422` al normalizar | XML sin diagrama, vacío, o `c4_level` fuera de 1–3. |
| Error `requiere C4NORM_LLM_API_KEY` (422 en API) | `--classifier llm`/`auto` sin clave: defínela o usa `heuristic`. |
| Timeout o error de red al clasificar | Diagrama muy grande (>20 nodos por lote). La segunda llamada es automática; si persiste, prueba `--classifier heuristic`. |
| El LLM devuelve tipos distintos a la heurística | Normal — el LLM puede mejorar la clasificación (p.ej. distinguir Person vs Software System). Verifica el resultado en draw.io. |
| `lxml` no instala | Usa Python 3.11/3.12 (no 3.14). |
