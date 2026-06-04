"""
Generación de diagrama desde texto (descripción de arquitectura → XML Draw.io crudo).

Un LLM convierte una descripción textual de arquitectura en un mxGraphModel XML,
que luego se procesa con el pipeline normal ``c4norm.normalize()``.

Misma configuración que el clasificador/visión:
  * ``C4NORM_LLM_API_BASE``   — endpoint OpenAI-compatible
  * ``C4NORM_LLM_API_KEY``    — clave de API
  * ``C4NORM_TEXT_MODEL``     — modelo (por defecto: el de C4NORM_LLM_MODEL)
  * ``C4NORM_TEXT_TIMEOUT``   — timeout (s)

Inject ``chat`` para tests o proveedores sin red.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from c4norm.vision import _env_int, _strip_fences

if TYPE_CHECKING:
    from collections.abc import Callable

_TEXT_SYSTEM = """\
Eres un experto en arquitectura de software (modelo C4 de Simon Brown) y en el
formato XML de draw.io (diagrams.net).

Tarea: a partir de una DESCRIPCIÓN TEXTUAL de una arquitectura, producir el XML
draw.io (mxGraphModel) de su diagrama C4 al nivel solicitado.

ESTRUCTURA DEL XML que debes producir:

<mxGraphModel>
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
    <!-- nodo simple -->
    <mxCell id="n1" value="Nombre" style="rounded=1;" vertex="1" parent="1">
      <mxGeometry x="100" y="100" width="160" height="80" as="geometry"/>
    </mxCell>
    <!-- contenedor / boundary / sitio (sus hijos usan su id como parent) -->
    <mxCell id="c1" value="NombreZona" style="swimlane;" vertex="1" parent="1" container="1">
      <mxGeometry x="0" y="200" width="400" height="300" as="geometry"/>
    </mxCell>
    <mxCell id="n2" value="HijoDeLaZona" style="rounded=1;" vertex="1" parent="c1">
      <mxGeometry x="20" y="40" width="120" height="60" as="geometry"/>
    </mxCell>
    <!-- arista con etiqueta -->
    <mxCell id="e1" value="usa" edge="1" source="n1" target="n2" parent="1">
      <mxGeometry relative="1" as="geometry"/>
    </mxCell>
  </root>
</mxGraphModel>

REGLAS ESTRICTAS:
1. IDs únicos y simples: n1, n2... (nodos); e1, e2... (aristas); c1, c2... (contenedores).
2. Modela SOLO lo que la descripción menciona. NO inventes sistemas, componentes ni
   conexiones que el texto no indique. Si un dato falta, omítelo (no lo fabriques).
3. Bases de datos / almacenes: style="shape=cylinder".
4. Personas / actores / usuarios: style="shape=mxgraph.c4.person".
5. Agrupadores (sitios, módulos, capas, namespaces): style="swimlane" y container="1";
   los elementos internos usan el id del agrupador como parent.
6. Las aristas reflejan las relaciones descritas; pon una etiqueta corta con la acción.
7. Ajusta el grano al nivel C4 pedido (1=sistemas, 2=contenedores, 3=componentes,
   4=código/componentes detallados).
8. Responde ÚNICAMENTE con el XML, sin backticks ni texto adicional.
"""


class TextExtractor:
    """
    Convierte una descripción textual de arquitectura en XML Draw.io crudo vía LLM.

    El XML resultante se alimenta directamente a ``c4norm.normalize()``.
    """

    def __init__(
        self,
        *,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        chat: Callable[[str], str] | None = None,
        timeout: float | None = None,
        retries: int = 2,
    ) -> None:
        self.api_base = api_base or os.environ.get("C4NORM_LLM_API_BASE", "https://api.openai.com/v1")
        self.api_key = api_key if api_key is not None else os.environ.get("C4NORM_LLM_API_KEY", "")
        self.model = model or os.environ.get("C4NORM_TEXT_MODEL") or os.environ.get("C4NORM_LLM_MODEL", "gpt-4o-mini")
        self.timeout = timeout if timeout is not None else _env_int("C4NORM_TEXT_TIMEOUT", 120)
        self.retries = retries
        self._chat = chat

    def generate(self, description: str, c4_level: int = 2) -> str:
        """
        Genera XML Draw.io crudo a partir de la descripción.

        Args:
            description: texto de la arquitectura a diagramar.
            c4_level: nivel C4 objetivo (1-4); se incluye en el prompt.

        Returns:
            mxGraphModel XML listo para ``c4norm.normalize()``.
        """
        if not description.strip():
            raise ValueError("La descripción de arquitectura está vacía.")

        chat = self._chat if self._chat is not None else self._llm_chat
        if self._chat is None and not self.api_key:
            raise ValueError(
                "TextExtractor requiere C4NORM_LLM_API_KEY (o inyectar 'chat'). "
                f"Modelo configurado: {self.model}."
            )

        user_msg = (
            f"Genera el diagrama C4 nivel {c4_level} de la siguiente arquitectura.\n\n"
            f"DESCRIPCIÓN:\n{description}"
        )

        last_exc: Exception | None = None
        for _attempt in range(self.retries + 1):
            raw = chat(user_msg)
            xml = _strip_fences(raw)
            if "<mxGraphModel" in xml or "<mxCell" in xml:
                return xml
            last_exc = ValueError(f"El LLM no produjo XML Draw.io: {xml[:200]!r}")
            user_msg += "\n\nIMPORTANTE: devuelve ÚNICAMENTE XML válido comenzando con <mxGraphModel>."
        raise ValueError(f"TextExtractor: respuesta inválida tras {self.retries + 1} intentos: {last_exc}")

    def _llm_chat(self, prompt: str) -> str:  # pragma: no cover - requiere red
        import httpx

        try:
            response = httpx.post(
                f"{self.api_base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": _TEXT_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=self.timeout,
            )
        except httpx.RequestError as exc:
            raise ValueError(f"TextExtractor: error de red al contactar {self.api_base}: {exc}") from exc
        if not response.is_success:
            raise ValueError(f"TextExtractor: el proveedor devolvió {response.status_code}: {response.text[:300]}")
        return str(response.json()["choices"][0]["message"]["content"])
