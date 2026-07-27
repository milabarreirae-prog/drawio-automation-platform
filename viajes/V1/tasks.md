---
title: "V1 — Tasks (checklist vivo del viaje del arquitecto)"
tags: [viaje, tasks, colmena-2.0, arquitecto, c4norm, drawio-automation-platform]
viaje: V1
dueño: drawio-automation-platform
fecha: 2026-07-18
---

# ✅ V1 — Tasks (checklist vivo)

> [!todo] Un constructor SOLO corre si esta lista tiene tasks abiertas (D1). Marca `[x]` sólo
> contra código vivo y recorrido en frío real (drive de `python -m c4norm` o del servidor
> `uvicorn`), jamás contra narrativa de board. Ver [[viajes/V1/spec|spec.md]] /
> [[viajes/V1/plan|plan.md]].
>
> **Estado de honestidad:** las 4 rebanadas están **TODAS ABIERTAS** hoy (2026-07-18) — ninguna
> tiene trabajo iniciado. Cada task trae DADO/CUANDO/ENTONCES o ruta+aserción del test futuro (DoR
> de `AUDITORIA_PRODUCTO_2026-07-16_spec-del-viaje.md`, ítem 6), no sólo una frase de alcance.

## Rebanada B-03 — API async ⏳ ABIERTA

- [ ] **Migrar el cliente LLM a `httpx.AsyncClient`.**
      DADO el clasificador actual (`c4norm/classify.py`) que hoy invoca el LLM de forma síncrona,
      CUANDO se reemplaza esa llamada por `httpx.AsyncClient`,
      ENTONCES `tests/test_llm_classifier.py` sigue en 12 passed sin regresión, y un nuevo test
      unitario confirma que la función expone una firma `async def` invocable con `await`.
- [ ] **Migrar los endpoints de `api/main.py` a async.**
      DADO `POST /api/v1/diagram/from-text` (hoy síncrono),
      CUANDO se declara como `async def` y usa el clasificador async de la task anterior,
      ENTONCES `tests/test_api.py` (clase `TestNormalize`) sigue en verde sin regresión.
- [ ] **Recorrido en frío: concurrencia real no serializa.**
      Ruta futura: `tests/test_api_async_recorrido_frio.py`.
      DADO un servidor `uvicorn` real (no `TestClient`) sirviendo `api/main.py`, con el LLM
      reemplazado por un stub que duerme una latencia fija simulada,
      CUANDO se lanzan N requests concurrentes reales (vía `httpx.AsyncClient` de prueba) a
      `POST /api/v1/diagram/from-text`,
      ENTONCES el tiempo total del lote es ≈ la latencia máxima de un solo request (no la suma de
      las N latencias) — aserción concreta: `tiempo_total < 1.5 * latencia_individual`.
- [ ] **Load-test con número de carga objetivo.**
      DADO que el "Por qué" de B-03 declara "escalamiento corporativo", pero sin RPS/concurrencia
      objetivo definido todavía (deuda declarada en `plan.md`),
      CUANDO la fundadora o el enjambre escalen un número concreto,
      ENTONCES esta task se reemplaza por un DADO/CUANDO/ENTONCES con ese número — **hasta
      entonces queda explícitamente bloqueada, no se cierra con un target inventado.**

## Rebanada B-04 — ETL LeanIX ⏳ ABIERTA

- [ ] **Pipeline GraphQL → modelo lógico contra fixture grabado.**
      Ruta futura: `tests/test_etl_leanix_recorrido_frio.py`.
      DADO un fixture de respuesta GraphQL de `falabella.leanix.net` grabado en
      `tests/fixtures/` (sin credenciales reales embebidas — S4),
      CUANDO se ejecuta el pipeline ETL completo hasta alimentar `c4norm.ground`,
      ENTONCES el diagrama resultante, pasado por `XMLLinter` (`api/linting.py`), es COMPLIANT o
      trae únicamente hallazgos "por validar" — cero violación de tipado inventado.
- [ ] **Ningún secreto de LeanIX en el repo.**
      DADO el fixture de la task anterior,
      CUANDO se corre el gate 2 de `.githooks/pre-push` (grep de secretos) sobre el commit que lo
      introduce,
      ENTONCES el gate pasa en verde — cero patrón de credencial (`sk-`, `AKIA`, URL con
      credenciales) detectado en el fixture ni en el código del ETL.
- [ ] **Auth real contra LeanIX — BLOQUEADA por dependencia externa.**
      DADO que la autenticación federada (SSO) contra `falabella.leanix.net` está fuera de este
      viaje (ver FUERA-como-deuda en `spec.md`, dueño: aranha-robots, patrón WF-002B),
      CUANDO aranha-robots publique el conector/token federado,
      ENTONCES esta task se abre con el DADO/CUANDO/ENTONCES concreto contra LeanIX real —
      **hasta entonces permanece bloqueada, no se simula una autenticación que no existe.**

## Rebanada B-05 — Sink Obsidian ⏳ ABIERTA

- [ ] **Generar `.md` con frontmatter + embed, de forma aislada.**
      Ruta futura: `tests/test_sink_obsidian_recorrido_frio.py`.
      DADO un diagrama C4 ya emitido por `c4norm.emit` en una carpeta temporal de prueba,
      CUANDO se invoca el exportador de sink sobre ese diagrama,
      ENTONCES se genera un archivo `.md` con frontmatter YAML parseable y una línea
      `![[<nombre>.drawio]]` cuyo path resuelve a un archivo real existente en la misma carpeta —
      verificado abriendo el `.md` generado y resolviendo el path, no sólo comprobando ausencia de
      excepción.
- [ ] **Contrato del vault — BLOQUEADA por dependencia externa.**
      DADO que la escritura real dentro del vault de Obsidian está fuera de este viaje (ver
      FUERA-como-deuda en `spec.md`, dueño: knowledge-base-personal-obsidian),
      CUANDO esa célula publique el contrato del sink (ruta, convención de frontmatter, mecanismo
      de entrega),
      ENTONCES esta task se abre con el DADO/CUANDO/ENTONCES concreto contra el vault real —
      **hasta entonces permanece bloqueada.**

## Rebanada B-06 — `wiki/REQUERIMIENTOS_v1.md` ⏳ ABIERTA

- [ ] **Redactar RF/RNF con ID trazable, a partir de lo ya construido.**
      DADO el código vivo actual de `c4norm`/`api` y los docs de diseño existentes
      (`docs/C4_NORMALIZER_DESIGN.md`, `docs/DESIGN.md`),
      CUANDO se redacta `wiki/REQUERIMIENTOS_v1.md` con cada RF/RNF numerado,
      ENTONCES cada ID citado trae al menos una referencia a un test real existente en `tests/`
      que lo cierra (no una descripción sin ancla verificable).
- [ ] **Escribir el verificador de trazabilidad.**
      Ruta futura: `scripts/verificar_trazabilidad_requerimientos.py`.
      DADO `wiki/REQUERIMIENTOS_v1.md` con IDs de RF/RNF,
      CUANDO se corre el script contra `tests/`,
      ENTONCES reporta cero RF/RNF huérfano (sin test) — y si encuentra alguno, falla con exit
      distinto de 0 (no advertencia muda).
- [ ] **Extender RF/RNF a B-03/B-04/B-05 a medida que avancen.**
      DADO que B-03/B-04/B-05 están hoy ABIERTAS sin código nuevo,
      CUANDO cualquiera de ellas cierre su primera task real,
      ENTONCES `wiki/REQUERIMIENTOS_v1.md` se actualiza en el mismo ciclo con el RF/RNF
      correspondiente — no se acumula deuda documental silenciosa.

## 🌱 Semilla del borde (para el próximo disparo)

Ninguna rebanada tiene trabajo iniciado. Candidata a tomar primero, según `plan.md` (ruta crítica
propuesta): **B-03, primera task** ("migrar el cliente LLM a `httpx.AsyncClient`") — sin
dependencia externa, apalanca a B-04 si su volumen crece. Alternativa: **B-06, primera task**
(redactar RF/RNF de lo ya existente) puede correr en paralelo sin bloquear nada.

## 🔗 Conexiones Relacionadas

- [[viajes/V1/spec|Spec de V1 — el qué]]
- [[viajes/V1/plan|Plan de V1 — el cómo]]
- [[../plans/board|Board de la célula (tabla BACKLOG original)]]
- `.hive/portfolio/COLMENA_2.0_MIGRACION.md` (Decreto Colmena 2.0)
