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
| `--org TEXTO` | (vacío) | Cajetín: organización (ISO 7200) |
| `--doc-no TEXTO` | (vacío) | Cajetín: número de plano (ISO 7200) |

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
| `c4_level` | 1·2·3·4 | 2 | Nivel C4 (4 = código; el motor modela hasta Component) |
| `classifier` | heuristic·llm·auto | heuristic | Clasificador |
| `title_block` | objeto | null | `project, title, doc_type, drawn_by, approved_by, date, revision, organization, doc_number` |
| `run_compliance_check` | bool | false | Corre el linter de compliance sobre la salida |
| `context` | string | "" | Documento de dominio (texto) que el LLM usa para enriquecer (ver §10) |
| `enrich` | bool | false | Activa la pasada de enriquecimiento con IA (requiere `C4NORM_LLM_API_KEY`) |

Respuesta:

```json
{
  "xml_c4": "<mxfile> … </mxfile>",
  "report": {
    "diagram_name": "Arquitectura N2", "c4_level": 2,
    "node_count": 6, "annotation_count": 0, "edge_count": 5, "inferred_edges": 0, "grounded_nodes": 0,
    "merged_nodes": 0, "enriched": false,
    "type_histogram": {"Person": 1, "Container": 4, "Database": 1},
    "low_confidence": [], "changelog": [], "scale": "1:1", "overflow": false,
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

### POST /api/v1/diagram/from-image  y  POST /api/v1/diagram/from-text

Generan el C4 desde una **imagen** o una **descripción textual** (vía LLM). Requieren `C4NORM_LLM_API_KEY`.

```bash
# Desde texto (sólo la descripción de arquitectura)
curl -s http://localhost:8000/api/v1/diagram/from-text \
  -H "Content-Type: application/json" \
  -d '{"description":"Una API FastAPI que invoca un motor c4norm...","c4_level":4}'

# Desde imagen (PNG/JPEG/WebP en base64)
curl -s http://localhost:8000/api/v1/diagram/from-image \
  -H "Content-Type: application/json" \
  -d '{"image_base64":"<...>","prompt":"diagrama c4n1 con esto"}'
```

Campos: `from-text` → `description` + `c4_level` + `classifier` + `title_block` + `run_compliance_check`;
`from-image` → `image_base64` + `prompt` (detecta el nivel del prompt) + los mismos opcionales.

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
| `C4NORM_LLM_TIMEOUT` | 120 | Timeout (s) de cada llamada al LLM |
| `C4NORM_LLM_BATCH_SIZE` | 20 | Nodos por lote enviados al LLM |
| `C4NORM_LLM_MAX_PARALLEL` | 4 | Lotes del LLM procesados en paralelo |
| `C4NORM_VISION_TIMEOUT` | 120 | Timeout (s) de la llamada de visión |

### Concurrencia y rendimiento

- Los lotes del clasificador LLM se procesan **en paralelo** (hasta `C4NORM_LLM_MAX_PARALLEL`):
  un diagrama de 60 nodos con `batch_size=20` hace 3 llamadas concurrentes en vez de 3 en serie.
- Los endpoints que llaman al LLM (`/normalize` con `classifier=llm`, `/from-image`) son
  síncronos: FastAPI los ejecuta en su **threadpool** (no bloquean `/health` ni `/metrics`).
  Bajo alta concurrencia de llamadas LLM lentas, el threadpool puede saturarse; en producción
  conviene limitar con `uvicorn --limit-concurrency N` y/o escalar horizontalmente.

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

## 9. Anotaciones (notas, textos, leyendas)

Un diagrama crudo suele traer **documentación** que no es arquitectura: post-its
(`shape=note`), títulos y rótulos de texto suelto (`style=text`) y bloques de
**leyenda** (swimlane llamado «Leyenda», «Notas» o «Convenciones», con sus celdas
de ejemplo). c4norm las detecta y las trata como una **capa de anotaciones**:

- **No** se clasifican como nodos C4 (no entran en `type_histogram` ni en
  `node_count`; se cuentan aparte en `annotation_count`).
- Se **preservan tal cual** —etiqueta y estilo originales— y se reubican en una
  banda bajo el diagrama, conservando su disposición relativa.
- Las aristas que apuntaban a una anotación se descartan (no son relaciones C4).

Así el modelo C4 queda limpio sin perder la documentación del autor. Las celdas
emitidas llevan el id prefijado `anno-`.

> **Invariante de anidamiento.** Un nodo con hijos siempre se emite como
> `DeploymentNode` (el único tipo *boundary* del estándar). Si un clasificador
> —p.ej. el LLM— degrada una zona contenedora a un tipo hoja, el motor lo corrige
> y lo avisa en `report.warnings`, evitando que los hijos queden sobre una caja sólida.

## 10. Enriquecimiento con IA (`enrich=true`)

Con `enrich=true` (y `C4NORM_LLM_API_KEY`), tras clasificar se ejecuta una pasada de
LLM que **potencia** el diagrama usando el campo `context` como **dominio del proyecto**
(p.ej. el catálogo de componentes en texto). El LLM:

- **Nutre** descripciones y tecnologías de los nodos existentes con el contexto.
- **Estandariza** nombres y **fusiona** duplicados evidentes (re-apunta sus aristas).
- **Mejora** las descripciones de las relaciones.
- **Integra lo no-C4 de forma estándar**: el **título** va al cajetín (deja de flotar);
  la **leyenda** original (cuyos colores ya no aplican) se reemplaza por una **clave C4
  limpia** generada con los tipos presentes; las **notas** se reescriben concisas.

Sigue el principio **«el motor nunca inventa»**: no añade nodos ni inyecta estado futuro
(To-Be); lo que infiere del contexto y no consta en el diagrama lo marca `(por validar)`,
y **cada cambio** queda en `report.changelog`. Es una llamada de LLM con prompt grande,
así que puede tardar (sube `C4NORM_LLM_TIMEOUT` si hace falta). El `context` es texto: si
tu fuente es un PDF, extrae el texto antes (la API no parsea PDFs).

```bash
curl -s http://localhost:8000/api/v1/diagram/normalize \
  -H "Content-Type: application/json" \
  -d '{"xml_content":"<mxGraphModel>...</mxGraphModel>","c4_level":3,
       "classifier":"auto","enrich":true,"context":"Catálogo de componentes: ..."}'
```

## 11. Principio: el motor nunca inventa

c4norm preserva y eleva lo que existe; lo que falta lo marca, no lo fabrica. La
metadata epistémica (`Confianza: Baja`, `Estado CMDB: Pendiente`) se conserva en la
descripción del nodo/relación.

## 12. Problemas frecuentes

| Síntoma | Causa / solución |
|---------|------------------|
| `layout_engine: layered` en vez de `elk` | Falta Node/elkjs: `npm install --prefix c4norm/layout` o define `C4NORM_NODE_BIN`. |
| Acentos rotos (`PeticiÃ³n`) | Mojibake del round-trip de Confluence; c4norm lo sanea al parsear. |
| `422` al normalizar | XML sin diagrama, vacío, o `c4_level` fuera de 1–3. |
| Error `requiere C4NORM_LLM_API_KEY` (422 en API) | `--classifier llm`/`auto` sin clave: defínela o usa `heuristic`. |
| Timeout o error de red al clasificar | Diagrama muy grande (>20 nodos por lote). La segunda llamada es automática; si persiste, prueba `--classifier heuristic`. |
| El LLM devuelve tipos distintos a la heurística | Normal — el LLM puede mejorar la clasificación (p.ej. distinguir Person vs Software System). Verifica el resultado en draw.io. |
| `lxml` no instala | Usa Python 3.11/3.12 (no 3.14). |
