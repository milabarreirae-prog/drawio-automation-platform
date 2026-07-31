# Política de datos — ingesta LeanIX (HU-ARQ-D2)

> **Estado:** DECIDIDA en sus legs de ingeniería (minimización enforced + retención);
> la **base de licitud** nace `por validar` — requiere visado de la **FUNDADORA**
> (titular de la decisión de base de licitud, Ley 21.719), con **revisión interna previa
> de lider-DPO-transversal**, antes de conectar el tenant real. Ax-C4N-001: el motor nunca
> inventa; una conclusión jurídica autoafirmada es contenido de consecuencia y se marca,
> no se da por cierta.
>
> **Solicitud de visado elevada:** `2026-07-29` — ver
> [`SOLICITUD_VISADO_LICITUD_LEANIX.md`](SOLICITUD_VISADO_LICITUD_LEANIX.md). El reloj de
> B-04b (`recheck_by: 2026-08-03`) corre contra este gate re-anclado a la fundadora, no
> contra el gate fantasma anterior (HU-ARQ-D2b, VALIDACION líder-arquitectura 2026-07-29).
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

### 2.1 Escalares consumidos pero NO solicitados (rotulados a propósito — HU-QA-D05)

`inventory_to_diagram` lee de `raw` dos escalares que `FACTSHEETS_QUERY` **no pide**
(no están en `FACTSHEETS_FIELD_PURPOSE`). No son campos PII colados por accidente — son
consumo-sin-pedir, cada uno con su propia decisión honesta, rotulados aquí para que no
se evaporen en silencio:

| Escalar | Se consume en | Decisión honesta |
|---------|----------------|-------------------|
| `external` | `inventory_to_diagram` (`bool(raw.get("external"))`, línea ~252) | NO se pide → en producción siempre `None`→`False`: **un sistema externo no-Provider jamás se marca `external=True` = pérdida de fidelidad silenciosa**. `por validar` — pedir `external` es un campo **nuevo** (requiere propósito + visado de política, gate D2); `recheck_by 2026-08-03` (junto a B-04b). No se auto-añade: el motor no inventa una decisión de política. |
| `name` | `inventory_to_diagram` (`raw.get("name")`, línea ~244) | Fallback muerto: `displayName` siempre se pide → nunca dispara en producción. Se conserva como no-op defensivo, documentado; su remoción sería higiene de motor (tarea B futura), fuera del alcance de este cierre QA. |

Diente que lo ancla: `tests/test_leanix_minimization.py::test_every_consumed_raw_scalar_is_accounted_for`
— un `raw.get()` nuevo sin pedir ni rotular pone rojo.

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

## 4. Base de licitud (`por validar` — visado de la FUNDADORA, revisión previa lider-DPO-transversal)

> Esta sección enumera las bases *candidatas* bajo la Ley 21.719 (protección de datos
> personales, Chile) y la lógica de por qué el tratamiento debería ser lícito. **No es un
> dictamen legal.** Nace `sin_verificar`: el motor no inventa una conclusión jurídica.
> Debe ser **ratificada por la FUNDADORA** — titular de la decisión de base de licitud en
> este ecosistema (no existe asesoría legal / DPO externa: anclar el gate a un actor
> inexistente lo convierte en gate fantasma que nunca abre, HU-ARQ-D2b) — con
> **lider-DPO-transversal** como revisión interna previa, antes de conectar el tenant real
> (precondición de B-04b). Solicitud elevada `2026-07-29`
> (`SOLICITUD_VISADO_LICITUD_LEANIX.md`).

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
  `por validar` por la FUNDADORA (revisión previa lider-DPO-transversal).
- **Deberes acompañantes:** minimización (§2, cumplida en código), finalidad declarada
  (§2), retención limitada (§3). Falta el visado humano de licitud.

## 5. Estado de cierre de HU-ARQ-D2

| Leg | Estado |
|-----|--------|
| Allow-list de campos con justificación | ✅ enforced en código + diente que muerde |
| Política de retención de artefactos derivados | ✅ escrita (§3); plazo concreto `por validar` |
| Base de licitud escrita | ✅ escrita (§4) pero `por validar` — **gate humano: FUNDADORA** (revisión previa lider-DPO-transversal); solicitud elevada `2026-07-29` |

**Conclusión honesta:** los legs de ingeniería de D2 quedan cerrados y verificados; el
único pendiente es la **ratificación de la base de licitud por la FUNDADORA** (titular de
esa decisión bajo la Ley 21.719, con lider-DPO-transversal en revisión interna previa),
que es gate humano y precede a B-04b. El gate estaba antes anclado a «asesoría legal/DPO»
—actor inexistente en este ecosistema = gate fantasma que nunca abre— y quedó re-anclado a
la fundadora (HU-ARQ-D2b). La solicitud fue elevada el `2026-07-29`
(`SOLICITUD_VISADO_LICITUD_LEANIX.md`); el reloj de B-04b (`2026-08-03`) corre contra este
gate real. No se conecta el SSO real hasta ese visado.
