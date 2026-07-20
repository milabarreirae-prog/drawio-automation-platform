---
title: "V1 — El arquitecto deja de dibujar a mano lo que ya sabe el sistema"
tags: [viaje, spec, colmena-2.0, arquitecto, c4norm, drawio-automation-platform]
viaje: V1
actor: arquitecto (con un drawio crudo)
miel: "normalización fiel a C4 conformante (tipado, ISO 7200, sin inventar)"
dueño: drawio-automation-platform
fecha: 2026-07-18
origen:
  - "D1 (decreto Colmena 2.0, `.hive/portfolio/COLMENA_2.0_MIGRACION.md`, 2026-07-15): «cada viaje activo tiene `viajes/V<n>/spec.md` (qué + miel + FUERA-como-deuda), `plan.md` (cómo) y `tasks.md` (checklist vivo)... Un constructor SOLO corre si su spec tiene tasks abiertas.»"
  - "Autoridad del decreto (mismo documento, campo `autoridad`): «DECRETO de la fundadora (2026-07-15, sesión directa: \"no quiero experimentos, quiero que migres\")»."
  - "Voto propio ADOPTA_ADAPTADO en `colmena_2_0_ratificacion` (`plans/board.md`, entrada G-06, 2026-07-15 20:45 -0400): «D1 sin `viajes/spec`, equivalente = tabla BACKLOG [...] Corrección de mi viaje: cliente = **arquitecto con un drawio crudo**, miel = **normalización fiel a C4 firmado (ISO 7200) que no inventa** (no \"generar desde cero\"). Destila Ax-C4N-014.»"
  - "Siembra de esta tarea (`plans/board.md`, BACKLOG ítem D1, 2026-07-18): «`viajes/V1/spec.md` — adaptar la tabla BACKLOG a spec de viaje (Colmena 2.0, decreto fundadora: \"hacemos cera, no miel\"): cada tarea nombra su viaje y su miel; DoD = recorrido EN FRÍO en instrumento vivo. No reinventar: la tabla actual es la base.»"
estado: "V1 formalizado 2026-07-18; cliente + miel VALIDADOS contra el alma en vivo (README.md:1 / CLINE.md:8-12, Regla 123) y feromona VIAJE emitida en el ledger federado (../.hive/consensus/proposals.log) el 2026-07-20 — cierra el gap de sincronización que el hallazgo transversal viajes_validacion_vencida cazó (mi validación de 07-15 vivía sólo en pheromones local, no cruzaba a proposals.log). Las 4 rebanadas (B-03..B-06) heredadas de BACKLOG siguen abiertas, gateadas por precondición externa — ninguna tiene aún recorrido en frío propio."
---

# 🍯 V1 — "El arquitecto deja de dibujar a mano lo que ya sabe el sistema"

> [!abstract] La unidad de trabajo (Colmena 2.0 · D1)
> Este `spec.md` adapta la tabla BACKLOG vigente de `plans/board.md` (B-03 a B-06) al molde
> spec-del-viaje. **No inventa alcance nuevo**: cada rebanada de abajo es, palabra por palabra en
> su "Por qué", la misma fila que ya vivía en el board. El **cómo** vive en
> [[viajes/V1/plan|plan.md]] y el checklist vivo en [[viajes/V1/tasks|tasks.md]]. Un constructor
> SOLO corre si esta spec tiene tasks abiertas (todas lo están hoy).
>
> **Nota de forma (honestidad de estado):** la Auditoría de Producto nº5
> (`.hive/proposals/AUDITORIA_PRODUCTO_2026-07-16_spec-del-viaje.md`, DoR de la spec-del-viaje,
> ítem 1) exige un actor **nombrado** ("Natalia", no una categoría). Este viaje NO tiene un
> arquetipo con nombre propio — usa el rol "arquitecto", tal como lo corrigió el propio voto G-06
> (Ax-C4N-014). Se marca **por validar** (no se oculta): si la fundadora o el enjambre proponen un
> nombre concreto, este campo se actualiza; hasta entonces, "arquitecto" es más concreto que "el
> usuario" pero no cumple el DoR estricto en su forma más alta.

## 👤 Quién y qué duele

El **arquitecto** llega con un **drawio crudo**: un diagrama dibujado a mano, sin tipado C4, sin
cajetín ISO 7200, sin escala declarada, con nodos y relaciones que "se entienden a simple vista"
pero que no sirven como artefacto firmable para auditoría, CMDB o handoff a otro equipo. Hoy ese
arquitecto pasa horas normalizando a mano — poniendo tipo a cada caja, agregando el cajetín,
alineando la jerarquía — y cada vez que lo hace a mano puede inventar sin darse cuenta (inferir un
tipo que el diagrama original no decía). No viene a pedir "un dibujo bonito nuevo": viene a que **lo
que ya dibujó** se vuelva conforme, sin que el sistema le mienta agregando lo que él no puso.

## 🎯 La miel (outcome — no la cera)

**Normalización fiel a C4 conformante (tipado, ISO 7200, sin inventar).** La cera (parsers, layout
ELK, clasificador heurístico/LLM, emisor XML) sólo existe para que esta miel ocurra. El motor
**nunca inventa**: todo lo que no puede probar con evidencia del propio drawio de entrada queda
marcado explícitamente como **"por validar"** en el diagrama emitido (badge de confianza/CMDB,
`c4norm/legend.py`), nunca como afirmación muda. Métrica de éxito humano: el drawio de salida es
firmable — trae cajetín ISO 7200 completo (autor/fecha/escala/revisión/estado/fuente), tipado C4
consistente, y cero elementos flotando sin padre válido (`repair_dangling_parents`,
`c4norm/parse.py`).

## 🧊 El viaje EN FRÍO (DoD real — instrumento vivo, sin UI propia)

Este motor es **raw→C4 headless, sin frontend humano propio** (ya declarado N/A honesto en el voto
G-06, D2a: "motor raw→C4 sin UI, análogo = drive-real `python -m c4norm`"). El equivalente al
"click-only desde `/`" de una célula con UI es un **drive real del instrumento vivo** — CLI
(`python -m c4norm`) o API (`POST /api/v1/diagram/from-text`, `api/main.py`) ejecutado de punta a
punta contra un drawio/fixture real, sin mockear el motor interno. HECHO = el recorrido corre en
frío sobre el instrumento vivo, no sólo tests unitarios en aislamiento.

```
drawio crudo (entrada real, sin tipado)
  → parseo (c4norm/parse.py: fix_mojibake, repair_dangling_parents, reconnect_orphan_edges)
  → clasificación (c4norm/classify.py: heurístico + LLM opcional, nunca inventa tipo inválido)
  → anclaje/enriquecimiento (c4norm/ground.py, c4norm/enrich.py)
  → layout (c4norm/layout: ELK persistente o fallback)
  → emisión C4 conformante (c4norm/emit.py: tipado + cajetín ISO 7200 + leyenda de gobernanza)
  → drawio de salida firmable, con "por validar" donde el motor no puede probar
```

## 🧱 Rebanadas (tabla BACKLOG heredada de `plans/board.md`, sin reinventar alcance)

| Rebanada | Descripción | Por qué | Esfuerzo | DoD |
|---|---|---|---|---|
| **B-03 · API async** | `httpx.AsyncClient` para las llamadas al LLM (clasificador); endpoints de `api/main.py` migrados a async | Escalamiento corporativo; validar con load-test, no de fe | L | ⏳ **EN DESARROLLO** — recorrido en frío futuro: `tests/test_api_async_recorrido_frio.py`. Criterio: DADO N requests concurrentes reales a `POST /api/v1/diagram/from-text` contra un servidor uvicorn vivo (no `TestClient` mockeado), CUANDO el LLM tarda una latencia simulada fija por request, ENTONCES el tiempo total del lote es ≈ la latencia máxima (no la suma) — prueba que el `AsyncClient` no serializa. Hoy: **ningún** recorrido en frío existe; los endpoints actuales son síncronos. |
| **B-04 · ETL LeanIX** | GraphQL `falabella.leanix.net` → modelo lógico → pipeline que nutre el clasificador/ancla de `c4norm` con inventario real | Nutre C4 del inventario real; el SSO lo resuelve aranha-robots (patrón WF-002B) — coordinar, no construir login propio | L | ⏳ **EN DESARROLLO** — recorrido en frío futuro: `tests/test_etl_leanix_recorrido_frio.py`. Criterio: DADO un fixture GraphQL grabado (respuesta real de LeanIX, sin credenciales embebidas — S4) CUANDO se ejecuta el pipeline ETL completo hasta `c4norm.ground`, ENTONCES el diagrama emitido pasa `XMLLinter` (`api/linting.py`) como COMPLIANT o marca "por validar" en lo que el ETL no pudo mapear — nunca inventa un componente que LeanIX no reportó. La autenticación real (SSO) queda FUERA de este viaje (ver sección siguiente). |
| **B-05 · Sink Obsidian** | Exportar diagramas como embeds `![[diagrama.drawio]]` + nota `.md` con frontmatter, para la bibliotecaria (knowledge-base-personal-obsidian) | Sinergia de la orquesta; esperar/coordinar el sink de knowledge-base | M | ⏳ **EN DESARROLLO** — recorrido en frío futuro: `tests/test_sink_obsidian_recorrido_frio.py`. Criterio: DADO un diagrama C4 ya emitido por `c4norm.emit`, CUANDO se invoca el exportador de sink, ENTONCES se genera un `.md` con frontmatter válido (YAML parseable) y un embed `![[archivo.drawio]]` cuyo path referenciado existe en disco en la misma corrida — verificado abriendo el `.md` generado y resolviendo el path, no solo comprobando que la función no lanzó excepción. La escritura real dentro del vault de la bibliotecaria queda FUERA (ver sección siguiente). |
| **B-06 · `wiki/REQUERIMIENTOS_v1.md`** | RF/RNF trazados, si el escalamiento corporativo lo exige | Completar GENESIS; hoy los docs de diseño (`docs/C4_NORMALIZER_DESIGN.md`, `docs/DESIGN.md`) cubren la mayor parte | S | ⏳ **EN DESARROLLO** — no es código, es documento; recorrido en frío futuro reemplazado por verificación de trazabilidad: `scripts/verificar_trazabilidad_requerimientos.py` (por escribir). Criterio: DADO `wiki/REQUERIMIENTOS_v1.md` con cada RF/RNF con ID único, CUANDO se corre el verificador contra `tests/`, ENTONCES cada ID aparece citado en al menos un test real — cero RF/RNF huérfano (sin test que lo cierre) y cero test sin RF/RNF que lo origine, en la medida en que el trabajo ya cubierto por B-03/B-04/B-05 lo permita. |

## 🚫 FUERA de V1 — descope firmado como DEUDA (no silencio)

> [!important] Descope = deuda con dueño y condición de reapertura verificable (no solo fecha)
> - **UI propia (dashboard/frontend visual)**: el motor es headless raw→C4, sin superficie humana
>   propia (decisión de arquitectura ya declarada N/A honesto en G-06, D2a). — dueño: n/a (decisión
>   de diseño, no deuda pendiente) · reapertura: si el enjambre decide que `drawio-automation-platform`
>   necesita front propio, se abre como viaje nuevo, no como parche de V1.
> - **SSO/login real contra LeanIX** (`falabella.leanix.net`, parte de B-04): el motor consume el
>   modelo lógico ya autenticado; NO construye su propio flujo de login. — dueño: **aranha-robots**
>   (patrón WF-002B) · reapertura: cuando aranha-robots entregue el conector/token federado, B-04 lo
>   consume; hasta entonces B-04 solo puede avanzar contra fixtures grabados, no contra LeanIX real.
> - **Escritura real en el vault de Obsidian** (parte de B-05): este viaje genera el artefacto
>   (`.md` + embed); no gestiona el vault, su índice ni su sincronización. — dueño:
>   **knowledge-base-personal-obsidian** (la bibliotecaria) · reapertura: cuando esa célula defina el
>   contrato del sink (ruta, convención de frontmatter, mecanismo de entrega), B-05 se ajusta a él.
> - **Escalamiento corporativo medido con load-test real** (B-03): "L" de esfuerzo declarado, pero
>   sin número de carga objetivo (RPS, concurrencia esperada) todavía escalado por la fundadora —
>   **por validar**, no asumido de fe. — dueño: drawio-automation-platform (esta célula) · reapertura:
>   cuando exista un número de carga concreto, la task de B-03 se re-escribe con ese target.
> - **Dato de dominio real** (diagramas bancarios, inventario LeanIX real, secretos): invariante viva
>   del núcleo — "jamás cruza al `.hive` común" — no es deuda de este viaje, es restricción permanente
>   (`plans/board.md`, sección "Restricciones vivas").
> - **`.github/workflows/` y Dependabot**: prohibidos por mandato de la fundadora, no forman parte de
>   ningún mecanismo de este viaje (ni siquiera para CI de las rebanadas nuevas).

## 🔍 Verificador (Regla 123: verificador ≠ autor)

Quien construya cada rebanada (B-03/B-04/B-05/B-06) **no** cierra su propio recorrido en frío. Sigue
el patrón ya practicado por esta célula en B-08 y B-11 (`plans/board.md`, entradas VERIFICADO): un
**subagente de contexto limpio** (independiente, sin haber visto la implementación) corre el drive
real del instrumento vivo (CLI/API) y confirma con salida citada — no con narrativa — que:
1. el camino verde funciona (no-regresión sobre lo ya VERIFICADO),
2. el camino rojo es rojo (adversarial: entrada que debe fallar, falla como se espera), y
3. el motor no inventó nada que el drawio/fixture de entrada no sustente.

Yo (quien construyó este `spec.md`) no soy el verificador de ninguna rebanada — este documento
declara el rol, no lo ejerce.

## 🔗 Conexiones Relacionadas

- [[viajes/V1/plan|Plan de V1 — el cómo]]
- [[viajes/V1/tasks|Tasks de V1 — checklist vivo]]
- [[../plans/board|Board de la célula (fuente de la tabla BACKLOG heredada)]]
- [[../CLINE.md|Núcleo de la célula]]
- `.hive/portfolio/COLMENA_2.0_MIGRACION.md` (Decreto Colmena 2.0, D1)
- `.hive/proposals/AUDITORIA_PRODUCTO_2026-07-16_spec-del-viaje.md` (DoR de la spec-del-viaje, usado
  como referencia de forma para este documento)
