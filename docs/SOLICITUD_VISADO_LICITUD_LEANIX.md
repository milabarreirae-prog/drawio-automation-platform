# Solicitud de visado de base de licitud — ingesta LeanIX (HU-ARQ-D2b)

- **Fecha de elevación:** `2026-07-29`
- **Dirigida a:** **FUNDADORA** (titular de la decisión de base de licitud, Ley 21.719)
- **Revisión interna previa:** lider-DPO-transversal
- **Origen:** VALIDACION líder-arquitectura-transversal 2026-07-29 (instrucción 1: gate
  legal re-anclado — un gate anclado a «asesoría legal/DPO», actor inexistente en este
  ecosistema, es gate fantasma que nunca abre)
- **Reloj:** precondición del gate **B-04b** (SSO federado real `falabella.leanix.net`,
  `recheck_by: 2026-08-03`). El SSO real **no se conecta** hasta este visado.

## Qué se pide ratificar

Que el tratamiento descrito en [`POLITICA_DATOS_LEANIX.md`](POLITICA_DATOS_LEANIX.md) tiene
base de licitud suficiente bajo la **Ley 21.719** para conectar el tenant productivo. En
concreto:

1. **Naturaleza del dato:** el inventario LeanIX ingerido es dato de **arquitectura
   corporativa** (aplicaciones, componentes, objetos de dato, proveedores) de titularidad
   de la propia organización — en principio **no personal**.
2. **Minimización ya cableada (§2, con diente):** c4norm solicita **sólo** `id`, `type`,
   `displayName`, `description` y referencias de grafo (`factSheet { id }`). La allow-list
   `FACTSHEETS_FIELD_PURPOSE` está enforced en código; la denylist PII (`owner`,
   `subscriptions`, `contacts`, `email`, `costs`, `lifecycle`, …) muerde en test aunque se
   le declare propósito.
3. **Retención (§3):** motor *stateless* — no persiste inventario crudo ni derivado; sin
   caché; cortafuegos federado (ningún dato de tenant cruza al `.hive`).
4. **Punto abierto que requiere tu decisión:** confirmar que `displayName`/`description`
   del tenant **no portan dato personal** en la práctica; y, si se detectara dato personal
   residual, ratificar la base candidata (interés legítimo del responsable) y sus deberes.

## Estado (honestidad de estado — Ax-C4N-001)

La base de licitud nace `por validar`. **El motor no inventa un dictamen jurídico**: esta
solicitud eleva la decisión a quien la tiene (la fundadora), no la da por cierta. Hasta la
ratificación, B-04b permanece gateado.

## Traza

- Re-anclaje registrado en `POLITICA_DATOS_LEANIX.md` §4 y §5 (gate humano = FUNDADORA).
- Board: ítem HU-ARQ-D2b (`plans/board.md`).
- Ledger federado: ACUSE dirigido a líder-arquitectura-transversal con esta fecha visible.
