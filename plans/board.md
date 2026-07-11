---
title: Board — drawio-automation-platform
tags: [board, kanban, c4norm]
actualizado: 2026-07-10
---

# 📋 Board vivo — c4norm

> Regla: UNA tarea atómica por ciclo. Verificar antes de mover a VERIFICADO
> (pytest verde + honestidad de estado). `main` solo recibe por merge desde `dev`.

## 🔴 BACKLOG (impacto/esfuerzo, del centro al borde)

| ID | Tarea | Por qué | Esfuerzo |
|----|-------|---------|----------|
| B-01b | **Fila de leyenda para los badges** (clave que explica `Confianza` / `Estado CMDB`) en `legend.py`, sólo si algún nodo la trae | Cierra el badge por-nodo (B-01a) con su convención; el dato ya vive estructurado en el modelo | S |
| B-02 | **Proceso Node persistente para ELK** (hoy arranca un Node por diagrama, ~100-400 ms) | Rendimiento; prerequisito razonable del async | M |
| B-03 | **API async** (`httpx.AsyncClient` para LLM; endpoints async) | Escalamiento corporativo; validar con load-test, no de fe | L |
| B-04 | **ETL LeanIX** (GraphQL `falabella.leanix.net` → modelo lógico → pipeline) | Nutre C4 del inventario real; el SSO lo resuelve aranha-robots (patrón WF-002B) — coordinar, no construir login propio | L |
| B-05 | **Sink Obsidian**: exportar diagramas como embeds `![[diagrama.drawio]]` + nota `.md` con frontmatter, para la bibliotecaria | Sinergia de la orquesta; esperar/coordinar el sink de knowledge-base | M |
| B-06 | `wiki/REQUERIMIENTOS_v1.md` (RF/RNF trazados) si el escalamiento corporativo lo exige | Completar GENESIS; hoy los docs de diseño cubren la mayor parte | S |

## 🟡 EN CURSO
*(vacío — sembrar desde BACKLOG al abrir el próximo ciclo; sugerida: B-01b)*

## 🟢 VERIFICADO
| Tarea | Evidencia |
|-------|-----------|
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
