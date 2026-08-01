# ADR-001: Política de datos para ingesta LeanIX (Ley 21.719, Chile)

**Date**: 2026-08-01
**Status**: DECIDIDA (en sus legs de ingeniería — minimización enforced + retención; base de licitud *por validar*, pendiente visado de la FUNDADORA)
**Decisión**: c4norm solicita **sólo** los campos que un diagrama C4 necesita (`id`, `type`, `displayName`, `description` + referencias de grafo `factSheet { id }`), con una allow-list cableada (`FACTSHEETS_FIELD_PURPOSE`) que construye `FACTSHEETS_QUERY` y una denylist PII con diente en test; el artefacto derivado es efímero (motor stateless, sin caché de inventario) y ningún dato de tenant cruza al `.hive` compartido.
**Alternativas evaluadas**: No se evaluaron alternativas formalmente; la política se redactó para cumplir Ley 21.719 como restricción no-negociable. La minimización no es una promesa en prosa — está cableada: `FACTSHEETS_QUERY` se construye desde `FACTSHEETS_FIELD_PURPOSE` (no se puede pedir un escalar sin declararlo) y `tests/test_leanix_minimization.py` muerde si aparece un campo fuera de la allow-list o un nombre de la denylist PII conocida (`owner`, `subscriptions`, `contacts`, `email`, `costs`, `lifecycle`, …), aunque alguien le declare un propósito.
**Contexto**:
- `c4norm/leanix.py` ingiere el inventario de FactSheets de un tenant LeanIX (`falabella.leanix.net`) y lo transforma en un diagrama C4 (XML drawio).
- La auditoría de arquitectura r.19 halló (HU-ARQ-D2, ALTA · Legal) que la política de datos debía escribirse antes de conectar el SSO real.
- La base de licitud nace *por validar* — el motor no inventa un dictamen jurídico. Solicitud de visado elevada `2026-07-29` a la FUNDADORA (titular de la decisión, con revisión interna previa de lider-DPO-transversal); ver `docs/SOLICITUD_VISADO_LICITUD_LEANIX.md`.
- Precondición dura del gate B-04b (SSO federado real, `recheck_by: 2026-08-03`): el SSO real no se conecta sin esta política aprobada.

**Consecuencias**:
- **Permitido:** solicitar `id`, `type`, `displayName`, `description` y referencias `factSheet { id }` — cada uno con su finalidad declarada en `FACTSHEETS_FIELD_PURPOSE`.
- **Prohibido (diente en test):** solicitar campos de la denylist PII (`owner`, `subscriptions`, `contacts`, `email`, `costs`, `lifecycle`, etc.) — el test de minimización falla aunque alguien declare un propósito.
- **Efímero por defecto:** `leanix_to_c4()` produce el XML y no persiste el inventario crudo ni el derivado; la respuesta GraphQL cruda no se escribe a disco. Sin caché de inventario.
- **Cortafuegos federado:** ningún dato de tenant cruza al `.hive` compartido (sólo método). Regla vigente de esta célula.
- **Derivados que el operador exporte:** heredan la clasificación del tenant y se retienen sólo mientras dure la finalidad del diagrama. Plazo concreto *por validar* (lo fija la política corporativa/legal del tenant, no c4norm).
- **Pendiente humano:** la ratificación de la base de licitud por la FUNDADORA (revisión previa lider-DPO-transversal). Sin ese visado, B-04b permanece gateado.
- **Escalares consumidos pero no solicitados (HU-QA-D05):** `external` y `name` se leen de `raw` pero `FACTSHEETS_QUERY` no los pide — rotulados a propósito, no se auto-añaden (el motor no inventa una decisión de política). `external` requiere propósito + visado; `name` es fallback muerto (no-op defensivo).
