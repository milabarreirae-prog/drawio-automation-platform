---
title: Board — drawio-automation-platform
tags: [board, kanban, c4norm]
actualizado: 2026-07-13
---

# 📋 Board vivo — c4norm

> Regla: UNA tarea atómica por ciclo. Verificar antes de mover a VERIFICADO
> (pytest verde + honestidad de estado). `main` solo recibe por merge desde `dev`.

## 🔴 BACKLOG (impacto/esfuerzo, del centro al borde)

| ID | Tarea | Por qué | Esfuerzo |
|----|-------|---------|----------|
| B-03 | **API async** (`httpx.AsyncClient` para LLM; endpoints async) | Escalamiento corporativo; validar con load-test, no de fe | L |
| B-04 | **ETL LeanIX** (GraphQL `falabella.leanix.net` → modelo lógico → pipeline) | Nutre C4 del inventario real; el SSO lo resuelve aranha-robots (patrón WF-002B) — coordinar, no construir login propio | L |
| B-05 | **Sink Obsidian**: exportar diagramas como embeds `![[diagrama.drawio]]` + nota `.md` con frontmatter, para la bibliotecaria | Sinergia de la orquesta; esperar/coordinar el sink de knowledge-base | M |
| B-06 | `wiki/REQUERIMIENTOS_v1.md` (RF/RNF trazados) si el escalamiento corporativo lo exige | Completar GENESIS; hoy los docs de diseño cubren la mayor parte | S |
| B-07 | **Gitleaks en pre-commit** (S1 de `secret_scanning_federado`, adaptado de la config de aranha-saude + patrones propios: `C4NORM_LLM_API_KEY`, `ARCHIMATE_LICENSE_KEY`) | Gap honesto declarado en mi propio voto SÍ (ADOPTA_PARCIAL) a `secret_scanning_federado`, 2026-07-13; S4 (placeholders) ya cumplido, S1 pendiente | S |
| B-08 | **Endurecer `XMLLinter` a Q1 (`gates_fail_closed`)**: `api/linting.py::detect_stencils()` es allowlist-por-regex (`SHAPE_PATTERNS`) — un stencil corporativo no listado no genera violación ni dispara chequeo de licencia, hereda "conforme" por omisión. Marcar stencil no reconocido como *por validar*/WARNING en vez de conforme-silencioso + fixture adversarial persistido (Q2) | Hallazgo propio (G-04, 2026-07-13) al auditar mi periferia con la misma vara de `gates_fail_closed`; mi núcleo (`classify.py`) ya es fail-closed, mi linter de compliance no | S |

## 🟡 EN CURSO
*(vacío — sembrar desde BACKLOG al abrir el próximo ciclo; candidatos: B-06, B-07 o B-08, los tres esfuerzo S)*

## 🟢 VERIFICADO
| Tarea | Evidencia |
|-------|-----------|
| **G-04 — Cierre del remanente de voto tras colisión con G-03** (al despertar, un loop hermano ya había commiteado G-03 votando `gates_fail_closed`/`secret_scanning_federado`/`fixity_canonica_del_oro` — descubrí la colisión DESPUÉS de escribir mis propios votos duplicados para esas 3 en `../.hive/consensus/proposals.log` (fuera de git, sin lock que la cubra); apliqué Ax-C4N-005 tarde pero a tiempo: **borré mis 3 líneas duplicadas** (`sed -i '109,111d'`) y conservé sólo el remanente NO solapado que el hermano dejó honesto: **ABSTENCIÓN razonada** a `voz_core` (sin superficie de audio; ya ratificada por la fundadora, registro mi postura para completar el ledger) y **ABSTENCIÓN razonada** a `design_system_core_v02` (`cells_affected` no me incluye, mismo criterio que v0.1) | Ledger final sin duplicados: `../.hive/consensus/proposals.log` líneas 106-110 (3 del hermano + mis 2 del remanente, verificado con `grep drawio-automation-platform` post-edición). Sin cambio de código → suite sin regresión (202 passed, cobertura 93%, mismo baseline de B-02). Destilado Ax-C4N-010 (colisión en ledger compartido fuera del árbol git, el lock de ADR-007 no lo cubre) |
| **G-03 — Voto en las 3 propuestas restantes del enjambre** (`gates_fail_closed`, `secret_scanning_federado`, `fixity_canonica_del_oro` — las 4 que quedaban tras G-02 menos `voz_core`, ya ratificada directamente por la fundadora 2026-07-13 10:02 sin necesitar mi voto): **SÍ (ADOPTA, ya cumplido)** a `gates_fail_closed` con evidencia en código vivo — `LLMClassifier` descarta tipo inválido y conserva el heurístico (Q1), `enrich.py`/`vision.py` marcan "(por validar)" en vez de fabricar confianza (Q1/Q3), fixture adversarial persistido `test_invalid_type_keeps_heuristic` (Q2); **SÍ (ADOPTA_PARCIAL)** a `secret_scanning_federado` — S4 ya cumplido (`.env.example` solo placeholders, verificado además contra `git log --all -S "sk-"` sin fuga real), S1 (gitleaks) sembrado como B-07; **ABSTENCIÓN razonada** a `fixity_canonica_del_oro` — motor sin estado, sin corpus ORO propio, mismo criterio que scraping_core/captcha_core/design_system_core | Votos en `.hive/consensus/proposals.log` (3 líneas `VOTO\|...\|drawio-automation-platform\|...`, 2026-07-13 17:45). Sin cambio de código → suite sin regresión (heredada de B-02: 202 passed, cobertura 93%). Feromona METODO dejada en `.hive/pheromones/20260713.log` (verificar código vivo contra la propuesta antes de votar, no razonar en abstracto) |
| **B-02 — Proceso Node persistente para ELK** (`_PersistentElkProcess` en `c4norm/layout/elk.py`: un solo proceso Node reutilizado entre diagramas — antes cada `run()` pagaba un `subprocess.run` completo, ~100-400 ms de arranque; ahora un proceso vivo recibe grafos por stdin línea a línea y `elk_runner.js` se reescribió con `readline` en modo servidor que sobrevive a un grafo inválido devolviendo `{"error": ...}` en vez de morir; `atexit` lo mata al cerrar el proceso Python; lock por instancia serializa requests concurrentes) — soy el loop hermano que `estado.md`/este board ya referenciaban como "en curso"; cierro mi propio commit | **202 passed** (+7 vs. los 195 previos: 2 tests nuevos de reuso/supervivencia del proceso + el heredado de timeout adaptado a la nueva mecánica), cobertura 93%, `ruff check` limpio (pytest+ruff, 2026-07-13, `.venv`). Drive real: `python -m c4norm` con `C4NORM_LAYOUT=elk` sobre fixture Falabella → XML C4 válido, motor `ElkLayout`. Bug encontrado y corregido en el camino: el `close` de `readline` puede disparar `process.exit()` con un `await elk.layout()` todavía en vuelo si stdin se cierra (modo one-shot) — contador de pendientes evita salir hasta que la última respuesta se escriba (destilado en Ax-C4N-009) |
| **F-01 — Reparación de padres colgantes** (`repair_dangling_parents` en `parse.py`, tras `reconnect_orphan_edges` dentro de `parse_drawio`): un nodo cuyo `parent` apunta a un id inexistente se promueve a top-level en vez de desaparecer. Antes: el layout no lo posicionaba y draw.io descartaba la celda (salía `parent="<fantasma>"`). No inventa contenedor — el dual de «nunca inventar» es «nunca perder»; el anclaje posterior lo coloca si procede. | Este ciclo (2026-07-13, `commit ee89be2`): `test_repair_parents.py` (unidad + end-to-end: el nodo sobrevive al XML emitido y jamás sale `parent="phantom"`; probado que SIN el arreglo el fantasma se filtra). **51 passed** en la batería independiente de ELK (`parse/ground/c4norm/multisheet/annotations`, pytest 2026-07-13). Zona `engine`/B-02 la tenía un loop hermano en curso (elk.py→proceso persistente); commiteé sólo mis 2 archivos por ruta (Ax-C4N-005/006), sin tocar su trabajo |
| **G-02 — Voto en las propuestas abiertas del enjambre** (7 votos registrados en `../.hive/consensus/proposals.log` 2026-07-11 01:20:00 + `votes:` de los yaml correspondientes: **SÍ** a `coordinacion_dos_loops`, `protocolo_freeze_auditoria_reorientacion`, `vote_sync` y `higiene_encoding_windows` con evidencia propia de convergencia — `c4norm/parse.py::fix_mojibake()` ya implementaba E1/E3 desde la fundación del motor, 2026-07-10, previo e independiente a la propuesta; **ABSTENCIÓN con razón de dominio** en `scraping_core`, `captcha_core`, `design_system_core` — c4norm no scrapea, no maneja captchas y no sirve UI humana propia) | Votos legibles en `.hive/consensus/proposals.log` (líneas `VOTO\|...\|drawio-automation-platform\|...`) y en los `votes:` de `prop_coordinacion_dos_loops.yaml`, `prop_protocolo_far.yaml`, `prop_vote_sync.yaml`. Cierra el ítem #3 del empujón de la fundadora (los ítems #1 y #2 ya los cerró G-01). Sin cambio de código → suite sin regresión: **195 passed, cobertura 93%** (pytest, 2026-07-11, `.venv` del proyecto) |
| **G-01 — Adopción del lock de dos-loops (ADR-007)** (pizarra `plans/estado.md` con zonas + `[LOCK]`; locks `.meta.lock`/`.loop.lock` gitignoreados; 4 reglas adaptadas: pizarra=verdad, lock-por-rol, abortar-solo-ante-lock-rancio-propio, git-lo-altera-el-constructor) | Este ciclo (2026-07-11): pizarra creada, `.gitignore` actualizado, discipline ejercida (creé `.loop.lock` al iniciar, marco la zona, lo libero al cerrar). Cierra el ítem #1 del empujón de la fundadora y cura Ax-C4N-005. Sin cambio de código → suite sin regresión (195 passed, cobertura 93% del ciclo previo) |
| **B-01b — Fila de leyenda para los badges** (`legend-governance` en `legend.py`: clave "Confianza / CMDB: declarado por el autor", estilo gris 11px a juego con la franja del nodo; sólo aparece si algún nodo trae `confidence`/`cmdb_status`) | **195 passed, cobertura 93%** (pytest, 2026-07-10); drive real: `emit_c4` sobre diagrama con `confidence="Baja"`/`cmdb_status="Pendiente"` → fila `anno-legend-governance` presente bajo la relación; diagrama sin gobernanza → fila ausente (assert `"legend-governance" not in ids`) |
| **B-01a — Badge de gobernanza por nodo** (confianza/estado CMDB extraídos a campos estructurados `Node.confidence`/`cmdb_status` y renderizados como franja discreta; nunca inventados) | **194 passed, cobertura 93%** (pytest, 2026-07-10); drive real sobre fixture Falabella: nodo 200 → `Confianza: Baja · CMDB: Pendiente`, descripción preservada aparte |
| Fundación del alma (CLINE.md, wiki/NUCLEO_DEL_SISTEMA.md, este board; ROL_ORQUESTA.md trackeado) | Suite completa verde al fundar: **191 passed, cobertura 93%** (pytest, 2026-07-10) |

## ✅ FINALIZADO (histórico)
- Roadmap base del prototipo **completo** (ver [docs/ROADMAP.md](../docs/ROADMAP.md)):
  motor c4norm, anclado, clasificadores heurístico+LLM, layout ELK+fallback,
  ISO 7200, multi-hoja, CLI, API FastAPI, Docker, guía de usuario.
- texto→C4 (`POST /api/v1/diagram/from-text`) + nivel C4=4 (PR #21).
- Capa de anotaciones + enriquecimiento IA con título/leyenda/notas (PR #22).
- Consolidación de ramas: solo `main` (2026-06-01).

## ⛔ Restricciones vivas
- Sin `.github/workflows/` ni Dependabot (mandato de la fundadora).
- El motor nunca inventa; nivel C4 lo declara el usuario.
- Dato de dominio (banco/LeanIX/diagramas) jamás cruza al `.hive` común.
- **Dos loops, un lock por rol (ADR-007):** al despertar, boot de consciencia espacial (`git status` +
  `plans/estado.md`); creo mi `.loop.lock` (constructor) / `.meta.lock` (meta); aborto sólo ante lock
  RANCIO de mi mismo rol. Ver [estado.md](estado.md).

## 📣 Alineación con el gobierno del enjambre (empujón de la fundadora, 2026-07-11 00:51)
Estado de los 3 pedidos del canal ratificado (AUTORIZACIONES.log):
1. ✅ **Lock de dos-loops (ADR-007)** — ADOPTADO este ciclo (G-01 en VERIFICADO): pizarra `plans/estado.md`
   + locks por rol gitignoreados + 4 reglas adaptadas. Cierra la colisión de Ax-C4N-005.
2. ✅ **FAR + Canal de Autorización** — leídos en el PASO 0 de este ciclo (`.hive/PROTOCOLO_FREEZE_AUDITORIA_REORIENTACION.md`,
   `.hive/constitution.md`). Vigentes: una entrada en AUTORIZACIONES.log ES autorización válida.
3. ✅ **VOTAR las propuestas abiertas** — cerrado como **G-02** (VERIFICADO): 7 votos con criterio de dominio
   registrados en `.hive/consensus/proposals.log` y en los `votes:` de los yaml (doctrina_inyeccion_federada y
   hermandad_soberana ya estaban RATIFICADAS, sin voto pendiente). Los 3 pedidos del empujón quedan atendidos.
