# ADR-002: Motor `c4norm` stateless (sin caller productivo persistente de `fetch_inventory`)

**Date**: 2026-08-01
**Status**: DECIDIDA
**Decisión**: El motor `c4norm` es stateless — `leanix_to_c4()` produce el XML y no persiste el inventario crudo ni el derivado, sin caché de inventario entre llamadas; coherente con esto, hoy no existe un caller productivo de `fetch_inventory(FACTSHEETS_QUERY)` (genotipo `la-primitiva-sin-caller`).
**Alternativas evaluadas**: No se evaluaron alternativas formalmente; el diseño stateless emergió del patrón de integración (CLI/API que recibe XML crudo y devuelve XML C4 en ms-segundos), no de un ADR previo con opciones comparadas. El contraste con la arquitectura anterior sí es documentable: la plataforma de rendering headless (worker async, cola ARQ/Redis, S3, webhooks) fue **eliminada** por no servir al requisito XML→XML (`ARCHITECTURE.md`), pero esa decisión fue sobre el rendering, no sobre la ingesta LeanIX.
**Contexto**:
- `c4norm` es un motor de normalización XML→XML: recibe XML crudo de Draw.io (típicamente generado por IA en formato libre) y produce XML C4 conforme a estándar, listo para Confluence.
- La API es FastAPI **síncrona** (`POST /api/v1/diagram/normalize`): el trabajo es de ms-segundos, no hay cola ni workers. CLI: `python -m c4norm <in.drawio.xml> --level {1|2|3} -o <out.xml>`.
- La ingesta LeanIX (`c4norm/leanix.py`) sigue el mismo patrón: pide el inventario, transforma, emite XML, devuelve. No persiste.
- Esto no es una promesa en prosa — está verificado en código: `ARCHITECTURE.md` §"Reutilización entre células" describe `c4norm` como "motor sin estado, consumido por su propia CLI/API"; `POLITICA_DATOS_LEANIX.md` §3 rotula "Efímero por defecto: el motor es *stateless*"; `plans/board.md` confirma "Hoy no hay caller productivo de `fetch_inventory(FACTSHEETS_QUERY)` (coherente con motor stateless)".
- `plans/board.md` (B-04b) anota como criterio de cierre TOTAL que el camino productivo consuma la QUERY generada del allow-list, no una paralela — y que hoy eso no existe (genotipo `la-primitiva-sin-caller`).

**Consecuencias**:
- **Sin caché de inventario:** no existe (ni debe crearse sin revisar la política de datos) un almacén persistente de FactSheets crudos. El único artefacto grabado es el fixture de prueba (`tests/fixtures/leanix_falabella.json`), dato de prueba controlado bajo control de versiones.
- **Sin cola ni workers:** la API síncrona procesa en ms-segundos; la arquitectura async anterior (ARQ/Redis/S3/webhooks) fue eliminada.
- **Cortafuegos federado:** ningún dato de tenant cruza al `.hive` compartido — coherente con la política de datos (ADR-001).
- **Proceso externo persistente (excepción acotada):** `_PersistentElkProcess` en `c4norm/layout/elk.py` sí mantiene un proceso Node vivo entre invocaciones (patrón "persistent worker process" para amortizar el arranque de Node/ELK), pero esto es estado de *proceso de layout*, no de inventario LeanIX ni de diagrama. No contradice el diseño stateless del motor de normalización.
- **Cableado productivo pendiente (B-04b):** el camino productivo de ingesta LeanIX aún no existe como caller de `fetch_inventory(FACTSHEETS_QUERY)` — cuando se conecte (precondición: visado de base de licitud), el criterio de cierre debe incluir que consume la QUERY del allow-list, no una paralela.
