---
title: Board — drawio-automation-platform
tags: [board, kanban, c4norm]
actualizado: 2026-07-11
---

# 📋 Board vivo — c4norm

> Regla: UNA tarea atómica por ciclo. Verificar antes de mover a VERIFICADO
> (pytest verde + honestidad de estado). `main` solo recibe por merge desde `dev`.

## 🔴 BACKLOG (impacto/esfuerzo, del centro al borde)

| ID | Tarea | Por qué | Esfuerzo |
|----|-------|---------|----------|
| G-02 | **Votar las 9 propuestas abiertas** (`../.hive/proposals/`: coordinacion_dos_loops, protocolo_far, captcha_core, scraping_core, design_system_core, vote_sync, higiene_encoding, doctrina_inyeccion_federada, hermandad_soberana) — voto con criterio de dominio, formato canónico, registrado | Ítem #3 del empujón de la fundadora; resolver los acuerdos del enjambre. Sólo cruza MÉTODO al común | S |
| B-02 | **Proceso Node persistente para ELK** (hoy arranca un Node por diagrama, ~100-400 ms) | Rendimiento; prerequisito razonable del async | M |
| B-03 | **API async** (`httpx.AsyncClient` para LLM; endpoints async) | Escalamiento corporativo; validar con load-test, no de fe | L |
| B-04 | **ETL LeanIX** (GraphQL `falabella.leanix.net` → modelo lógico → pipeline) | Nutre C4 del inventario real; el SSO lo resuelve aranha-robots (patrón WF-002B) — coordinar, no construir login propio | L |
| B-05 | **Sink Obsidian**: exportar diagramas como embeds `![[diagrama.drawio]]` + nota `.md` con frontmatter, para la bibliotecaria | Sinergia de la orquesta; esperar/coordinar el sink de knowledge-base | M |
| B-06 | `wiki/REQUERIMIENTOS_v1.md` (RF/RNF trazados) si el escalamiento corporativo lo exige | Completar GENESIS; hoy los docs de diseño cubren la mayor parte | S |

## 🟡 EN CURSO
*(vacío — sembrar desde BACKLOG al abrir el próximo ciclo; sugerida: B-02)*

## 🟢 VERIFICADO
| Tarea | Evidencia |
|-------|-----------|
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
3. 🔲 **VOTAR las propuestas abiertas** (`.hive/proposals/`: coordinacion_dos_loops, protocolo_far, captcha_core,
   scraping_core, design_system_core, vote_sync, higiene_encoding, doctrina_inyeccion_federada, hermandad_soberana)
   → sembrado como **G-02** en el BACKLOG para el próximo ciclo (una tarea atómica por ciclo; el voto emitido con
   criterio, formato canónico, y registrado).
