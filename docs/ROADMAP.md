# Hoja de ruta — drawio-automation-platform

> Diseño del motor: [C4_NORMALIZER_DESIGN.md](C4_NORMALIZER_DESIGN.md) · Diseño general: [DESIGN.md](DESIGN.md)

## Objetivo

Normalizar XML crudo de Draw.io (de IA) a **C4 conforme a estándar** para Confluence
(XML → XML), con el nivel C4 declarado por el usuario.

## ✅ Hecho

- Motor `c4norm`: parse + saneo (mojibake, formatos), modelo lógico, reparación de
  aristas huérfanas y contención solo-visual.
- **Anclado** de nodos de infra sueltos (Container/Database/Component) a una zona de
  conectividad cuando hay boundaries (idempotente).
- Clasificadores C4 tras la interfaz `C4Classifier`: **heurístico** (determinista) y
  **LLM** (OpenAI-compatible, provider-agnóstico; modos `heuristic` / `llm` / `auto`).
  El LLM solo re-tipa nodos existentes (no inventa); tipo inválido → conserva el heurístico.
- Layout intercambiable: **ELK real** (elkjs/Node, ruteo ortogonal) + **fallback** Python.
- Hoja de ingeniería: marco + **cajetín ISO 7200** + escala + ajuste al contenido.
- **CLI** (`python -m c4norm`) y **API** FastAPI síncrona (`POST /api/v1/diagram/normalize`,
  `/health`, `/metrics`, con auth opcional y rate limiting).
- **Contenedor** (Python + Node/elkjs) que sirve la API.

## ⏳ Pendiente

- **Multi-hoja**: cuando el contenido no cabe ni al mínimo se marca `overflow`; falta
  partir en varias hojas / vistas por boundary.
- **Documentación de usuario** (guía + ejemplos de la API).

## 🔭 Futuro (fuera del prototipo)

- Interop **LeanIX** (ETL GraphQL → modelo lógico → este pipeline).
- Badges / leyenda de estado (`Confianza`, `Estado CMDB`) en el diagrama.

## Principio innegociable

El motor **nunca inventa**: preserva y eleva lo que existe; lo que falta lo marca como
*por validar*. (C4_NORMALIZER_DESIGN.md §10.)
