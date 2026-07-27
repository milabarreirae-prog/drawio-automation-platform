---
title: "V1 — Plan (el cómo del viaje del arquitecto)"
tags: [viaje, plan, colmena-2.0, arquitecto, c4norm, drawio-automation-platform]
viaje: V1
dueño: drawio-automation-platform
fecha: 2026-07-18
estado: "stub — ninguna rebanada tiene ruta crítica ejecutada todavía"
---

# 🛠️ V1 — Plan (el *cómo*)

> [!info] Complementa a [[viajes/V1/spec|spec.md]] (el *qué*) y [[viajes/V1/tasks|tasks.md]] (el
> checklist). El plan sólo describe **cómo** se construye/verifica cada rebanada; ninguna decisión
> de negocio vive aquí (esa vive en la spec y en [[../CLINE.md|el núcleo]]).
>
> **Honestidad de estado:** este `plan.md` es un **stub**. Las 4 rebanadas heredadas de BACKLOG
> (B-03..B-06) están en `plans/board.md` sin trabajo iniciado — no hay todavía una secuencia
> probada, solo la propuesta de orden de abajo. Se actualizará con evidencia real cuando la
> primera rebanada empiece a moverse.

## Dependencias

| Rebanada | Depende de | Naturaleza de la dependencia |
|---|---|---|
| **B-03 (API async)** | Ninguna dependencia externa; depende del código actual de `api/main.py` (endpoints síncronos hoy) | Interna — puede empezar en cualquier momento |
| **B-04 (ETL LeanIX)** | **aranha-robots** (patrón WF-002B de SSO federado) para autenticación real contra `falabella.leanix.net` | Externa, **bloqueante para el recorrido en frío contra LeanIX real**; NO bloqueante para avanzar contra fixtures grabados (ver FUERA-como-deuda en spec.md) |
| **B-05 (Sink Obsidian)** | **knowledge-base-personal-obsidian** (la bibliotecaria) para el contrato del sink (convención de frontmatter, ruta del vault, mecanismo de entrega) | Externa, **bloqueante para la escritura real en el vault**; NO bloqueante para generar el `.md`+embed de forma aislada |
| **B-06 (REQUERIMIENTOS_v1)** | Ninguna dependencia externa dura; se beneficia de que B-03/B-04/B-05 ya tengan RF/RNF identificables para trazar | Interna — puede empezar en paralelo, pero su cobertura crece con el resto |

**Nota (por validar):** el contrato exacto que aranha-robots y knowledge-base-personal-obsidian van
a exponer todavía no está definido de este lado — esta tabla declara la dependencia, no la resuelve.
Si algún equipo publica su contrato antes de que esta célula lo pida, actualizar esta fila con la
referencia real (archivo/commit), no con "coordinado" a secas.

## Ruta crítica (propuesta, no ejecutada — reevaluable por ciclo)

**B-03 (API async) → B-06 (REQUERIMIENTOS_v1, parcial) → B-04 (ETL LeanIX, sólo fixtures) → B-05
(Sink Obsidian, sólo generación aislada)** — el resto de B-04/B-05 (recorrido en frío contra
sistemas reales) queda gated por las dependencias externas de la tabla anterior.

Razón del orden: B-03 no tiene dependencia externa y es la que más apalanca el resto (si el ETL de
B-04 termina generando volumen, necesita el motor ya async, no migrarlo después). B-06 puede correr
en paralelo desde el día uno porque documenta, no bloquea código. B-04/B-05 se llevan hasta donde el
fixture/aislamiento lo permite, sin esperar a que las otras dos células respondan.

## Cómo se verifica cada rebanada

- **Suite**: `python -m pytest` (`tests/`, ver `pyproject.toml` para configuración de cobertura).
  Cobertura actual del repo: 93% (línea base, `plans/board.md`, entrada B-11).
- **Estilo**: `ruff check` (ver mismas entradas del board para patrón de uso).
- **Instrumento vivo**: `python -m c4norm` (CLI) y `uvicorn api.main:app` (servidor real para
  `POST /api/v1/diagram/from-text`) — sobre ellos corre el drive real de cada recorrido en frío,
  nunca sólo `TestClient` mockeado cuando la rebanada lo permite.
- **Gate de secretos/toolchain**: `.githooks/pre-push` (gate 1 pytest, gate 2 grep de secretos,
  fail-closed ante toolchain ausente — B-07/B-08/B-11). Ninguna rebanada de V1 lo reemplaza ni lo
  bypassea; corre igual sobre el código nuevo de B-03..B-06.

## Invariantes que el cómo JAMÁS puede violar (del núcleo)

- **El motor nunca inventa**: todo lo que el drawio/fixture de entrada no sustenta se marca "por
  validar", nunca se afirma con confianza fabricada.
- **Nivel C4 lo declara el arquitecto**, el motor no lo infiere por su cuenta.
- **Dato de dominio jamás cruza al `.hive` común** (diagramas bancarios, inventario LeanIX real,
  secretos) — invariante permanente, no negociable por ninguna rebanada.
- **Sin `.github/workflows/` ni Dependabot** (mandato de la fundadora) — ninguna rebanada de V1
  introduce CI vía GitHub Actions, ni siquiera para B-03/B-04.

## Alternativas consideradas

- **Empezar por B-04 (ETL LeanIX) primero**, por ser la de mayor "por qué" declarado ("nutre C4 del
  inventario real"). Descartada como primera rebanada porque su recorrido en frío completo está
  gateado por una dependencia externa (aranha-robots) que esta célula no controla — arrancar por ahí
  arriesga quedar bloqueada sin poder cerrar ningún DoD real en el corto plazo.
- **Tratar B-06 (REQUERIMIENTOS_v1) como prerequisito de todo lo demás** (documentar antes de
  construir). Descartada por ir contra D2 del decreto (mecanismo sobre prosa): B-06 traza RF/RNF a
  tests reales, así que necesita que existan tests de B-03/B-04/B-05 para trazar contra algo, no al
  revés.

## Riesgos

- **Riesgo de "coordinar" sin fecha**: B-04 y B-05 dependen de contratos que otras dos células no
  han publicado. Si esas células no priorizan el contrato, este viaje queda con dos rebanadas
  permanentemente en "sólo fixtures/aislado" — deuda honesta declarada, no oculta, pero sin plazo de
  resolución garantizado.
- **Riesgo de LLM async mal medido (B-03)**: sin un número de carga objetivo (RPS/concurrencia)
  escalado por la fundadora, el DoD de "load-test real" puede quedar subjetivo — el criterio actual
  (tiempo total ≈ latencia máxima, no la suma) prueba que el `AsyncClient` no serializa, pero no
  prueba que el sistema aguante la carga corporativa real declarada en el "Por qué" de B-03.
- **Riesgo de deuda documental (B-06)**: si B-03/B-04/B-05 avanzan más rápido que B-06, el verificador
  de trazabilidad puede encontrarse con RF/RNF que ya deberían existir y no existen todavía — no es
  motivo para inventarlos retroactivamente, sino para declarar el hueco explícitamente en el propio
  `wiki/REQUERIMIENTOS_v1.md`.

## 🔗 Conexiones Relacionadas

- [[viajes/V1/spec|Spec de V1 — el qué]]
- [[viajes/V1/tasks|Tasks de V1 — checklist vivo]]
- [[../CLINE.md|Núcleo de la célula]]
- [[../plans/board|Board de la célula]]
- `.hive/portfolio/COLMENA_2.0_MIGRACION.md` (Decreto Colmena 2.0)
