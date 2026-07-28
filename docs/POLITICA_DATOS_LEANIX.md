# Política de datos — ingesta LeanIX (HU-ARQ-D2)

> **Estado:** DECIDIDA en sus legs de ingeniería (minimización enforced + retención);
> la **base de licitud** nace `por validar` — requiere visado de asesoría legal antes
> de conectar el tenant real. Ax-C4N-001: el motor nunca inventa; una conclusión
> jurídica autoafirmada es contenido de consecuencia y se marca, no se da por cierta.
>
> **Precondición dura del gate B-04b** (SSO federado real `falabella.leanix.net`,
> `recheck_by: 2026-08-03`): el SSO real NO se conecta sin esta política aprobada.
> Auditoría de arquitectura r.19, hallazgo HU-ARQ-D2 (ALTA · Legal).

## 1. Alcance

`c4norm/leanix.py` ingiere el inventario de FactSheets de un tenant LeanIX
(`falabella.leanix.net`) y lo transforma en un diagrama C4 (XML drawio). Esta política
cubre **qué** datos se solicitan, **por qué** (finalidad), **cuánto** se conservan los
artefactos derivados y **sobre qué base** se tratan.

## 2. Minimización y finalidad (enforced en código)

Principio: c4norm solicita **sólo** los campos que un diagrama C4 necesita. La
minimización no es una promesa en prosa — está **cableada y con diente**:

- **Fuente única de verdad:** `FACTSHEETS_FIELD_PURPOSE` (`c4norm/leanix.py`) declara
  cada campo escalar solicitado *con su propósito*. `FACTSHEETS_QUERY` se **construye**
  desde esas claves (`_build_factsheets_query`): no se puede pedir un escalar sin
  declararlo.
- **Piso duro:** `tests/test_leanix_minimization.py` MUERDE (rojo verificado en vivo por
  mutación) si aparece un campo escalar fuera de la allow-list o un nombre de la denylist
  PII conocida (`owner`, `subscriptions`, `contacts`, `email`, `costs`, `lifecycle`, …),
  **aunque** alguien le declare un propósito.

### Campos solicitados y su finalidad

| Campo | Finalidad (por qué c4norm lo necesita) | ¿Dato personal? |
|-------|----------------------------------------|-----------------|
| `id` | Identidad referenciable — sin id la relación cuelga (Ax-C4N-001) | No (identificador técnico de FactSheet) |
| `type` | Mapeo determinista LeanIX→C4Type (`LEANIX_C4_MAP`) | No |
| `displayName` | Nombre visible del nodo C4 | Improbable; nombre de sistema/componente. `por validar`: podría contener nombre de persona si el tenant lo usa mal |
| `description` | Descripción del nodo C4 | Improbable; texto de arquitectura. `por validar`: idem |

Relaciones (`relApplicationTo*`) traen **sólo** `factSheet { id }`: una referencia de
grafo, nunca un atributo del extremo.

**Campos NO solicitados (excluidos a propósito):** propietarios/responsables,
suscripciones, contactos, correos, usuarios creador/modificador, tags, costos, ciclo de
vida, documentos, comentarios. Son los que con mayor probabilidad portan dato personal o
de negocio ajeno a un diagrama de arquitectura.

## 3. Retención de artefactos derivados

El artefacto derivado (XML C4 / diagrama) puede reflejar `displayName` y `description`
del tenant. Política:

- **Efímero por defecto:** el motor es *stateless* — `leanix_to_c4()` produce el XML y
  no persiste el inventario crudo ni el derivado. La respuesta GraphQL cruda **no se
  escribe a disco** por c4norm.
- **Sin caché de inventario:** no existe (ni debe crearse sin revisar esta política) un
  almacén persistente de FactSheets crudos. El único artefacto grabado es el **fixture de
  prueba** (`tests/fixtures/leanix_falabella.json`), que es dato de prueba controlado, no
  el tenant productivo, y vive bajo control de versiones del repo.
- **Derivados que el operador exporte:** si un operador guarda el XML resultante, hereda
  la clasificación del tenant y se retiene **sólo mientras dure la finalidad** del
  diagrama; se purga al cerrarla. `por validar`: plazo concreto de retención lo fija la
  política corporativa/legal del tenant, no c4norm.
- **Cortafuegos federado:** ningún dato de tenant cruza al `.hive` compartido (sólo
  método). Regla vigente de esta célula.

## 4. Base de licitud (`por validar` — requiere asesoría legal)

> Esta sección enumera las bases *candidatas* bajo la Ley 21.719 (protección de datos
> personales, Chile) y la lógica de por qué el tratamiento debería ser lícito. **No es un
> dictamen legal.** Nace `sin_verificar`: el motor no inventa una conclusión jurídica.
> Debe ser **ratificada por asesoría legal / DPO** antes de conectar el tenant real
> (precondición de B-04b).

- **Naturaleza del dato:** el inventario LeanIX es dato de **arquitectura corporativa**
  (aplicaciones, componentes, objetos de dato, proveedores). En principio **no** es dato
  personal; la minimización de la sección 2 excluye deliberadamente los campos que sí lo
  serían. `por validar`: confirmar que `displayName`/`description` del tenant no portan
  dato personal en la práctica.
- **Base candidata:** tratamiento de dato **no personal** de titularidad de la propia
  organización, con finalidad de documentación de arquitectura interna. Si se confirma
  ausencia de dato personal, la Ley 21.719 no gobernaría el grueso del tratamiento.
- **Si se detectara dato personal residual** (p. ej. un nombre en un `displayName`): base
  candidata = interés legítimo del responsable (documentación de sus propios sistemas),
  sujeta a ponderación y a los deberes de información/minimización ya cubiertos.
  `por validar` por asesoría legal.
- **Deberes acompañantes:** minimización (§2, cumplida en código), finalidad declarada
  (§2), retención limitada (§3). Falta el visado humano de licitud.

## 5. Estado de cierre de HU-ARQ-D2

| Leg | Estado |
|-----|--------|
| Allow-list de campos con justificación | ✅ enforced en código + diente que muerde |
| Política de retención de artefactos derivados | ✅ escrita (§3); plazo concreto `por validar` |
| Base de licitud escrita | ✅ escrita (§4) pero `por validar` — **gate humano: asesoría legal/DPO** |

**Conclusión honesta:** los legs de ingeniería de D2 quedan cerrados y verificados; el
único pendiente es la **ratificación legal** de la base de licitud, que es gate humano y
precede a B-04b. No se conecta el SSO real hasta ese visado.
