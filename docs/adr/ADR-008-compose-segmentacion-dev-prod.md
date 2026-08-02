# ADR-008: Segmentación dev/prod del stack Docker Compose

**Date**: 2026-08-02
**Status**: DECIDIDA
**Decisión**: El stack queda definido por un compose base (`docker-compose.yml`, sin
puertos publicados y sin archivo de credenciales) + dos overrides —
`docker-compose.dev.yml` (bind loopback `127.0.0.1`, `C4NORM_ENV=dev`, env_file `.env`)
y `docker-compose.prod.yml` (bind `0.0.0.0` con justificación escrita, `C4NORM_ENV=prod`,
env_file `.env.prod`, límites `mem_limit: 2g` / `cpus: 2.0`). La API expone el entorno
en `GET /health` (campo `environment`) para que el operador sepa dónde está parado.
**Alternativas evaluadas**: (a) Compose *profiles* (`profiles: ["dev"]`) — descartado:
los profiles activan/desactivan servicios completos, no seleccionan configuraciones
distintas para el mismo servicio; el override es el mecanismo canónico de variación
por ambiente. (b) Un solo compose con variables interpoladas — descartado: el operador
no "sabe en qué ambiente está" por inspección, y el bind loopback vs 0.0.0.0 no se
declara explícitamente. (c) Dos compose completos independientes — descartado:
duplica build/image/restart. No se evaluaron formalmente más opciones.
**Contexto**: HU-ARQ-D4 (auditoría arquitectura r.19, 2026-07-27): un solo compose de
7 líneas, sin segmentación dev/prod, sin límites de recursos, `.env` único sin
distinción por ambiente; el operador no puede saber en qué ambiente está ni con qué
credenciales. Converge con Ax-SEC-001 (lider-seguridad, 2026-08-02): todo puerto de
stack de desarrollo local se ata explícitamente a loopback; publicar en 0.0.0.0
requiere justificación escrita.
**Consecuencias**:
- El comando para levantar el stack cambia: `docker compose -f docker-compose.yml -f docker-compose.dev.yml|prod.yml up`.
- Credenciales reales viven SOLO en `.env.prod` (gitignored); dev usa placeholders.
- Los límites de recursos de prod son valores de partida NO load-tested (gate B-03
  abierto); cuando exista número de carga objetivo, se revisan.
- `.env.prod` se agrega a `.gitignore` (el patrón `.env` no lo cubría — riesgo previo
  de commitear credenciales reales de prod).
