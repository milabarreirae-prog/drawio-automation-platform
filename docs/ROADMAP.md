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
- **Multi-hoja**: si desborda y hay ≥2 boundaries, descompone en una hoja por boundary
  (vista de deployment) + "Contexto"; las aristas que cruzan hojas se cuentan y reportan.
- **CLI** (`python -m c4norm`) y **API** FastAPI síncrona (`POST /api/v1/diagram/normalize`,
  `/health`, `/metrics`, con auth opcional y rate limiting).
- **Contenedor** (Python + Node/elkjs) que sirve la API.
- **Guía de usuario** (`docs/USER_GUIDE.md`): instalación, CLI, API, Docker, configuración y troubleshooting.
- **Badge de gobernanza por nodo** (`Confianza`, `Estado CMDB`): extraídos a campos
  estructurados (`Node.confidence`/`cmdb_status`) y renderizados como franja discreta en
  la etiqueta; ausente si el autor no lo declaró (B-01a, `plans/board.md`).

## ⏳ Pendiente

Ninguno — el roadmap base del prototipo está completo. ✅

## 🔭 Futuro (fuera del prototipo)

- Interop **LeanIX** (ETL GraphQL → modelo lógico → este pipeline).
- Fila de leyenda que explique los badges de `Confianza`/`Estado CMDB` (B-01b, `plans/board.md`).
- **Rendimiento avanzado** (requiere load-testing para validar):
  - API totalmente **async** (`httpx.AsyncClient`) para que las llamadas LLM no
    consuman un hilo del threadpool durante la espera de red.
  - **Proceso Node persistente** para ELK (evita el arranque de ~100-400 ms por diagrama).

## Principio innegociable

El motor **nunca inventa**: preserva y eleva lo que existe; lo que falta lo marca como
*por validar*. (C4_NORMALIZER_DESIGN.md §10.)
