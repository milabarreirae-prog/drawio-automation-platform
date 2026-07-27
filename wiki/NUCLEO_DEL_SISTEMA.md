---
title: NÚCLEO DEL SISTEMA — c4norm
tags: [nucleo, objetivo-inviolable, c4, drawio]
fecha: 2026-07-10
estado: FUNDADO
---

# 🎯 Núcleo del Sistema — c4norm

## Objetivo INVIOLABLE
> **Que cualquier XML crudo de Draw.io (típicamente generado por IA) entre por un
> comando o un endpoint y salga como diagrama C4 conforme a estándar — tipado,
> anclado, con layout limpio y cajetín ISO 7200 — sin que el motor invente jamás
> un solo elemento.**

Criterio de éxito medible: `python -m c4norm entrada.xml --level N` (o
`POST /api/v1/diagram/normalize`) produce XML que Confluence renderiza, donde cada
nodo tiene tipo C4 explícito, ninguna arista quedó huérfana, nada flota fuera de un
boundary, y todo lo no confirmado está marcado *por validar*.

## Arquitectura (autoritativa, no duplicar aquí)
- Pipeline y decisiones: [../docs/C4_NORMALIZER_DESIGN.md](../docs/C4_NORMALIZER_DESIGN.md)
- Vista general: [../ARCHITECTURE.md](../ARCHITECTURE.md)
- Hoja de ruta: [../docs/ROADMAP.md](../docs/ROADMAP.md)

```
parse → modelo lógico → clasifica (heurístico|LLM) → ancla → layout (ELK|Python) → emite C4 + ISO 7200
```

## Axiomas del dominio (disciplina de la arquitecta)
1. Un diagrama es un **grafo tipado firmado**: cajetín ISO 7200, escala, jerarquía;
   nada flotando.
2. El **nivel C4 lo da el usuario** (1–4); el motor no lo infiere.
3. **Nunca inventar**: el LLM solo re-tipa nodos existentes; tipo inválido →
   conserva el heurístico; lo faltante se marca *por validar*.
4. Las anotaciones humanas (notas, leyendas, títulos) se **preservan** en su capa,
   no se clasifican ni se pierden.

## Frontera de la célula
- **Es mi dominio**: normalización drawio→C4, texto→C4, imagen→C4, layout, hoja ISO,
  compliance, y las futuras integraciones LeanIX/CMDB como *fuentes* del modelo lógico.
- **NO es mi dominio**: orquestación n8n (aranha-forge), RPA/SSO (aranha-robots),
  vault Obsidian (knowledge-base-personal-obsidian). Con ellas me conecto, no las reemplazo.
