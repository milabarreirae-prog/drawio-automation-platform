# Motor de Normalización C4 — Diseño

**Estado:** Diseño (prototipo)
**Fecha:** 29 de Mayo, 2026
**Documentos relacionados:** [DESIGN.md](DESIGN.md) · [ROADMAP.md](ROADMAP.md)

> Este documento redefine el foco del proyecto a partir del requerimiento real,
> refinado en conversación. Sustituye conceptualmente el encuadre original de
> "FASE 9: Layout Automático (ELK)" del [ROADMAP.md](ROADMAP.md): el layout
> automático pasa a ser **una sub-etapa** de un motor mayor de normalización a C4.

---

## 1. Objetivo

**Entrada:** XML de Draw.io crudo, típicamente generado por IA en formato libre
(desordenado, sin estilo consistente, a veces estructuralmente incompleto).

**Salida:** XML de Draw.io conforme al estándar **C4** (la librería C4 de
diagrams.net), con acabado profesional, listo para **publicar en Confluence**
(que lo renderiza con su plugin de draw.io).

**Parámetro clave:** el usuario **declara el nivel C4 objetivo** (`1`, `2` o `3`).
El nivel determina qué tipos C4 se usan y cuán profundo se anida.

El entregable es **XML → XML**. NO se requiere renderizar a imagen para producirlo.

---

## 2. Reencuadre respecto a v0.1.0 (qué es núcleo y qué es "grasa")

El código actual (v0.1.0) es un **servicio de rendering** headless. Para el
objetivo XML→XML, buena parte no aplica:

| Componente v0.1.0 | ¿Núcleo para C4 XML→XML? |
|---|---|
| Parsing lxml, schemas Pydantic, patrón FastAPI, validación temprana | ✅ Reutilizable |
| Validación de compliance (colores/stencils/licencia) | ⚠️ Opcional/ortogonal |
| Worker headless (Chromium + Xvfb + Draw.io, ~1.2 GB) | ❌ Grasa (solo rasteriza) |
| ARQ + Redis (cola async) | ❌ Grasa (el layout es de ms-segundos) |
| S3/MinIO + webhooks | ❌ Grasa (Confluence renderiza) |
| Resolución de stencils + inyección `<mxLibrary>` | ❌ Grasa (en XML→XML los estilos se preservan/reescriben) |

El **render headless** queda como **etapa opcional de QA/preview** (generar un PNG
para revisar a ojo), no como el corazón del producto.

---

## 3. El estándar C4 (canónico, decodificado de la plantilla oficial draw.io)

C4 en draw.io **no** usa cajas sueltas con color arbitrario. Usa `<object>` con
**metadata tipada** y un `label` con *placeholders* que draw.io expande:

```xml
<object c4Name="API Service" c4Type="Container" c4Technology="Java/Python"
        c4Description="..." label="<b>%c4Name%</b><div>[%c4Type%: %c4Technology%]</div>...">
  <mxCell style="rounded=1;...;fillColor=#438DD5;fontColor=#ffffff;..." vertex="1">
    <mxGeometry .../>
  </mxCell>
</object>
```

El `c4Type` determina forma y color de forma fija:

| c4Type | Forma / color |
|---|---|
| **Person** | `shape=mxgraph.c4.person`, fill `#08427b` |
| **Software System** (interno) | rounded, fill `#1168BD` |
| **Software System** (externo) | rounded, fill `#999999` (gris) |
| **Container** | rounded, fill `#438DD5`, stroke `#3C7FC0` |
| **Component** | rounded, fill `#85BBF0` |
| **Database** | `shape=cylinder`, fill `#438DD5` (int) / `#999999` (ext) |
| **Relationship** | arista `#707070` punteada + `c4Technology` + `c4Description` |
| **DeploymentNode / ExecutionEnvironment** | caja blanca, borde negro, label arriba-izquierda |
| **Legend** | grupo con una muestra de cada tipo |

**Niveles:** N1 = sistemas (Person + Software System); N2 = se abren los sistemas
en Containers + Database; N3 = se abren los containers en Components. Los
swimlanes de sitio/cloud (DCC, CDLV, OCI, Azure…) mapean a **DeploymentNode**
(diagrama de deployment).

> Nota: los diagramas "pulcros" previos del equipo (`#dae8fc`, `#fff2cc`, …) **no
> eran C4 estricto** — eran ad-hoc. El estándar a imponer es **este** (paleta C4).

---

## 4. Arquitectura del pipeline (síncrona, ligera)

```
XML crudo (mxfile O mxGraphModel pelado)
  │
  ├─ 1. PARSE + NORMALIZAR ... aceptar ambos formatos; sanear encoding
  │       (mojibake del round-trip Confluence vía ftfy), entidades,
  │       shapes inválidos (cylinder3 → cylinder3d)
  │
  ├─ 2. MODELO LÓGICO ........ nodos, aristas, contención.
  │       Preferir estructura explícita (parent, source/target);
  │       geometría original como RESPALDO para inferir:
  │         • aristas huérfanas → enganche por proximidad
  │         • contención solo-visual → reparenting
  │       (debe ir ANTES del layout: la geometría original es la evidencia)
  │
  ├─ 3. CLASIFICAR a C4 ...... cada nodo → c4Type + c4Name + c4Description
  │       + c4Technology, según el nivel declarado.  ← NÚCLEO (ver §5)
  │
  ├─ 4. EMITIR C4 ............ reconstruir cada nodo como <object> + estilo
  │       canónico C4; aristas como Relationship; añadir Legend.
  │       (plantillado determinista una vez conocido el tipo)
  │
  ├─ 5. LAYOUT (ELK) ......... posiciones + ruteo ortogonal; respeta
  │       boundaries/DeploymentNodes (grafo compuesto)
  │
  └─ 6. SERIALIZAR .......... XML drawio válido para Confluence
```

---

## 5. Clasificador C4 — abstracción intercambiable (decisión clave)

El paso difícil no es la geometría; es **asignar el `c4Type`**. Se diseña como
una **interfaz** con varias implementaciones:

```
C4Classifier.classify(logical_model, c4_level) -> typed_model
```

- **`HeuristicClassifier`** (determinista, sin coste):
  - Si la IA **ya emitió `c4Type`** en el nodo → se respeta (camino rápido y de
    alta fidelidad; solo se corrige lo dudoso).
  - Si no → reglas por forma + etiqueta + metadata:
    `cylinder*` → Database; `umlActor`/`cloud` (persona/externo) → Person /
    Software System externo; `swimlane` → DeploymentNode; `Rol:`/`Confianza:`/
    `Estado CMDB:` → `c4Description`; etc.

- **`LLMClassifier`** (implementado, **API tipo OpenAI**, provider-agnóstico):
  - Para **corregir diagramas ya generados que están fuera de estándar**.
  - Arranca con la heurística (baseline de nombres/tech/desc) y pide al LLM revisar
    sólo el `c4Type`. **Nunca inventa**: tipo inválido → conserva el heurístico.
  - Proceso en lotes de ≤20 nodos con el grafo de aristas completo como contexto;
    reintentos ante JSON inválido.
  - Provider configurable por entorno (`C4NORM_LLM_API_BASE/KEY/MODEL`); probado con
    Alibaba Cloud MaaS (`qwen3.7-max`) y compatible con OpenAI, Azure OpenAI y
    cualquier endpoint `/chat/completions` con `response_format: json_object`.

**Estrategia (`classifier: "heuristic" | "llm" | "auto"`):** determinismo donde
se pueda; LLM para rellenar nodos de baja confianza o cuando el usuario pide
explícitamente "corregir fuera de estándar". El LLM es **opcional**: añade coste,
latencia y no-determinismo, por eso vive detrás de la interfaz.

---

## 6. API (implementada)

```
POST /api/v1/diagram/normalize
{
  "xml_content": "...",          // XML Draw.io crudo (mxfile | mxGraphModel)
  "c4_level": 2,                 // 1 | 2 | 3 (declarado por el usuario)
  "classifier": "heuristic",    // heuristic | llm | auto
  "title_block": { ... },       // opcional: project, title, doc_type, drawn_by, ...
  "run_compliance_check": false  // opcional: linter sobre el XML de salida
}
→ {
    "xml_c4": "...",
    "report": {
      "node_count",
      "annotation_count",   // notas/textos/leyendas preservados como capa aparte
      "edge_count", "inferred_edges", "grounded_nodes",
      "type_histogram", "low_confidence", "scale", "overflow",
      "sheet", "orientation", "engine",
      "sheets",             // hojas generadas (≥2 si hubo descomposición)
      "cross_sheet_edges"   // aristas que cruzan hojas (no se dibujan)
    },
    "compliance": null | { level, violations, ... }
  }
```

Síncrono (ms-segundos). Auth opcional por API key y rate limiting por IP.
Ver `docs/USER_GUIDE.md §4` para ejemplos completos.

---

## 7. Reparaciones (sub-etapas, mapeadas a defectos reales observados)

| Defecto observado en los ejemplos | Etapa | Técnica |
|---|---|---|
| Mojibake (`PeticiÃ³n`, `â¢`) — **lo introduce el round-trip de Confluence, no la IA** | 1 | `ftfy` + normalización Unicode |
| Formato pelado `<mxGraphModel>` sin `<mxfile>` | 1 | Normalización de envoltorio |
| `shape=cylinder3` (inválido) | 1 | Mapeo a `cylinder3d`/`cylinder` |
| Aristas huérfanas (solo `sourcePoint`/`targetPoint`) | 2 | Hit-test por proximidad a bounding-box |
| Contención solo-visual (caja dentro de swimlane pero `parent="1"`) | 2 | Reparenting por geometría |
| Grupos vacíos, coords negativas, waypoints duplicados, páginas casi-duplicadas | 2 | Limpieza / dedup |
| Cajas uniformes gigantes, sin ajuste al texto | 4 | Tamaño canónico C4 por tipo + ajuste al label |
| Sin paleta semántica | 3-4 | Clasificación C4 → estilo canónico |
| Notas/textos/leyendas tomados como componentes | 1 | Capa de anotaciones: se preservan aparte, no se clasifican |
| Zona contenedora degradada a tipo hoja (LLM) | 3 | Invariante: nodo con hijos → `DeploymentNode` |

---

## 8. Constraints y riesgos

- **Encoding del round-trip Confluence:** el input crudo de IA está en UTF-8
  correcto; el daño aparece al pasar por Atlassian. El saneo es necesario porque
  el destino es Confluence.
- **Calidad de clasificación** depende de las etiquetas. El LLM ayuda pero no es
  gratis → opcional y pluggable.
- **Escala (cientos de nodos):** la respuesta es **descomposición por
  nivel/boundary** (vistas C4), no un lienzo gigante. Ningún motor de layout
  hace "profesional" un grafo de 500 nodos en un solo canvas. *(Implementado:
  multi-hoja por boundary al desbordar — `c4norm/emit.py`.)*
- **Interop LeanIX (futuro):** fuera del prototipo. Cuando llegue, será un ETL
  GraphQL → modelo lógico → este pipeline; los `c4Type` se derivarían de las Fact
  Sheets. Los stencils LeanIX son propietarios.

---

## 9. Próximos pasos (spike)

1. **Spike de clasificación + emisión C4** sobre los crudos reales:
   - Crudo IA 2 (flujo simple) → C4 nivel 2 (Person/Container/Database).
   - Crudo IA 1 (multi-sitio) → C4 deployment nivel 2-3.
   - Validar que el XML resultante abre correcto en Confluence.
2. Definir la **interfaz `C4Classifier`** + `HeuristicClassifier` funcional.
3. Stub de `LLMClassifier` (interfaz + adaptador OpenAI-compatible) **sin**
   implementación productiva todavía.
4. ~~Integrar **ELK** como etapa de layout~~ ✅ **Hecho** — ver §11.

Fixtures sugeridas: guardar los XML de ejemplo de la conversación en
`tests/fixtures/` (crudos de IA + ejemplos C4 de referencia).

---

## 10. Disciplina de dibujo de ingeniería (requisito de la arquitecta)

Un diagrama de arquitectura no es un "dibujo": es un **grafo tipado con
información** y, sobre todo, un **artefacto firmado** — una representación de
verdad que ingenieros/arquitectos entregan a otros. De ahí, requisitos no
estéticos sino de disciplina (ISO/ANSI / vieja escuela):

- **Marco + cajetín ISO 7200** (implementado, `c4norm/sheet.py`): borde de hoja
  y viñeta con proyecto, título, tipo (As-Is/To-Be), dibujó, revisó/arquitecto,
  fecha, revisión, hoja N de M, formato (A3/A4) y **escala**.
- **Escala real** (implementada): el dibujo se ajusta a la hoja y la escala
  resultante se reporta en el cajetín (`1:1`, `1:1.9`…). Si no cabe ni al mínimo,
  se marca *overflow* y se descompone en multi-hoja por boundary.
- **Layout que refleja la jerarquía** (implementado: árbol vertical TB; futuro:
  ELK con minimización de cruces y ruteo ortogonal). Nunca "todo en una fila".
- **Nada flotando** (implementado): los nodos de infra sueltos
  (Container/Database/Component) se anclan en una zona de conectividad cuando hay
  boundaries (`c4norm/ground.py`); personas y sistemas pueden quedar fuera (C4 válido).

### Principio innegociable: el motor NUNCA inventa

Como el diagrama es verdad firmada, el motor **preserva y eleva lo que existe;
lo que falta lo marca como "por validar", jamás lo fabrica.** Inventar una ruta,
un proveedor o un puerto que no se validó violaría la firma. En consecuencia:

- Toda la información de las aristas (`TCP 16016`, `XA/Jolt`, `HTTPS`, `JDBC/ETL`)
  se conserva como `c4Technology`/`c4Description` de la relación.
- La metadata epistémica que la arquitecta ya anota (`Confianza: Baja`,
  `Estado CMDB: Pendiente`) es **de primera clase**: se conserva en
  `c4Description` y, a futuro, se renderiza como badge/leyenda de estado — no se
  descarta ni se entierra.
- Donde el estándar espera un dato ausente, se marca explícitamente (TBD / "por
  validar"), nunca se omite en silencio.

---

## 11. Motor de layout (implementado): ELK real + fallback

El layout es una **interfaz intercambiable** (`c4norm/layout/`):

- **`ElkLayout`** — ELK real (Eclipse Layout Kernel) vía **`elkjs` sobre Node**.
  Construye un grafo ELK jerárquico (boundaries = nodos compuestos), corre el
  algoritmo `layered` (dirección `DOWN`) con **ruteo ortogonal que esquiva las
  cajas**, y devuelve posiciones + *bend points* que se emiten como waypoints de
  las relaciones. Es el motor por defecto cuando Node + `elkjs` están presentes.
- **`LayeredLayout`** — fallback en **Python puro** (Sugiyama simple, sin
  dependencias): árbol vertical centrado + reducción de cruces por baricentro y
  ruteo por lado ("peine"). Se usa si ELK no está disponible.

Selección: `get_layout_engine()` elige ELK si está disponible; forzar con
`C4NORM_LAYOUT=elk|layered`. Node se localiza por `C4NORM_NODE_BIN`, luego PATH,
luego instalación winget portable.

**Puesta en marcha del puente ELK** (`c4norm/layout/`):
```
cd c4norm/layout && npm install   # instala elkjs (gitignored)
```
**Enterprise/Docker:** el `Dockerfile.worker` (o el de la API según dónde corra el
normalizador) debe instalar Node.js + ejecutar `npm install` en `c4norm/layout/`.
Sin Node, el motor degrada al fallback Python sin romperse.
