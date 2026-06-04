"""
Extracción de diagrama desde imagen (imagen + prompt → XML Draw.io crudo).

El LLM con visión analiza la imagen y produce un mxGraphModel XML que luego
se procesa con el pipeline normal ``c4norm.normalize()``.

Config por entorno (misma clave que el clasificador):
  * ``C4NORM_LLM_API_BASE``  — endpoint OpenAI-compatible
  * ``C4NORM_LLM_API_KEY``   — clave de API
  * ``C4NORM_VISION_MODEL``  — modelo de visión (por defecto: qwen-image-2.0-pro)

Inject ``chat`` para tests o proveedores sin red.
"""

from __future__ import annotations

import base64
import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def _env_int(name: str, default: int) -> int:
    """Lee un entero de entorno con fallback silencioso al default."""
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default

# =============================================================================
# Detección de nivel C4 desde prompt en lenguaje natural
# =============================================================================

_LEVEL_RE: list[tuple[re.Pattern[str], int]] = [
    # "c4n1", "C4 N 2", "c4n3"  → grupo de captura
    (re.compile(r'c4\s*n\s*([123])', re.I), 0),
    # "nivel 1", "nivel1"
    (re.compile(r'nivel\s*([1234])', re.I), 0),
    # "level 1", "level1"
    (re.compile(r'level\s*([1234])', re.I), 0),
    # "n1", "N2"  (palabra completa)
    (re.compile(r'\bn\s*([1234])\b', re.I), 0),
    # Palabras clave semánticas → nivel fijo
    (re.compile(r'\bcontexto\b', re.I), 1),
    (re.compile(r'\bcontenedores?\b', re.I), 2),
    (re.compile(r'\bcomponentes?\b', re.I), 3),
    (re.compile(r'\b(c[oó]digo|code|clases)\b', re.I), 4),
]

# C4 estándar: 4=Code. El motor modela hasta Component, así que N4 = vista más
# granular disponible (componentes/módulos de código).
_LEVEL_LABELS = {
    1: "contexto (sistemas)",
    2: "contenedores",
    3: "componentes",
    4: "código (componentes detallados — vista más granular del motor)",
}


def extract_level_from_prompt(text: str) -> int:
    """Extrae el nivel C4 (1-4) de un texto en lenguaje natural. Por defecto 2."""
    for pattern, fixed in _LEVEL_RE:
        m = pattern.search(text)
        if m:
            return fixed if fixed else int(m.group(1))
    return 2


# =============================================================================
# Prompt de sistema para el LLM de visión
# =============================================================================

_VISION_SYSTEM = """\
Eres un experto en arquitectura de software y en el formato XML de draw.io (diagrams.net).

Tarea: analizar la imagen de un diagrama de arquitectura y producir el XML \
draw.io equivalente en formato mxGraphModel.

ESTRUCTURA DEL XML que debes producir:

<mxGraphModel>
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
    <!-- nodo simple -->
    <mxCell id="n1" value="NombreExacto" style="rounded=1;" vertex="1" parent="1">
      <mxGeometry x="100" y="100" width="160" height="80" as="geometry"/>
    </mxCell>
    <!-- contenedor / zona / sitio (swimlane) — sus hijos usan su id como parent -->
    <mxCell id="c1" value="NombreZona" style="swimlane;" vertex="1" parent="1" container="1">
      <mxGeometry x="0" y="200" width="400" height="300" as="geometry"/>
    </mxCell>
    <mxCell id="n2" value="HijoDeLaZona" style="rounded=1;" vertex="1" parent="c1">
      <mxGeometry x="20" y="40" width="120" height="60" as="geometry"/>
    </mxCell>
    <!-- arista (edge) -->
    <mxCell id="e1" value="labelArista" edge="1" source="n1" target="n2" parent="1">
      <mxGeometry relative="1" as="geometry"/>
    </mxCell>
  </root>
</mxGraphModel>

REGLAS ESTRICTAS:
1. IDs únicos y simples: n1, n2... para nodos; e1, e2... para aristas; c1, c2... para contenedores.
2. Copia las etiquetas EXACTAMENTE como aparecen (incluyendo saltos, paréntesis, mayúsculas).
3. Bases de datos (cilindros): style="shape=cylinder"
4. Personas/actores: style="shape=mxgraph.c4.person"
5. Zonas/sitios con borde punteado: style="swimlane" y container="1"
6. Los hijos de un contenedor usan el id del contenedor como parent (no "1").
7. Conectores: incluye el label si tiene texto visible; si es ilegible usa "por validar".
8. NO inventes elementos que no veas.
9. Responde ÚNICAMENTE con el XML, sin backticks, sin texto adicional.
"""


# =============================================================================
# Helpers internos
# =============================================================================


def _mime_type(image_bytes: bytes) -> str:
    """Detecta el MIME type desde los magic bytes de la imagen."""
    if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if image_bytes[:3] == b'\xff\xd8\xff':
        return "image/jpeg"
    if image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        return "image/webp"
    return "image/png"  # fallback


def _strip_fences(raw: str) -> str:
    """Elimina bloques de código Markdown (```xml … ```) del output del LLM."""
    raw = raw.strip()
    if not raw.startswith("```"):
        return raw
    lines = raw.split("\n")
    inner_lines = lines[1:]
    inner = "\n".join(inner_lines)
    if inner.rstrip().endswith("```"):
        inner = inner.rstrip()[:-3]
    return inner.strip()


# =============================================================================
# VisionExtractor
# =============================================================================


class VisionExtractor:
    """
    Convierte una imagen de diagrama a XML Draw.io crudo usando un LLM con visión.

    El XML resultante puede alimentarse directamente a ``c4norm.normalize()``.

    Proveedores probados:
      - Alibaba Cloud MaaS: ``qwen-image-2.0-pro``, ``qwen-image-2.0``
      - OpenAI: ``gpt-4o``, ``gpt-4-turbo``
    """

    def __init__(
        self,
        *,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        chat: Callable[[bytes, str], str] | None = None,
        timeout: float | None = None,
        retries: int = 2,
    ) -> None:
        self.api_base = api_base or os.environ.get("C4NORM_LLM_API_BASE", "https://api.openai.com/v1")
        self.api_key = api_key if api_key is not None else os.environ.get("C4NORM_LLM_API_KEY", "")
        self.model = model or os.environ.get("C4NORM_VISION_MODEL", "qwen3.6-plus")
        self.timeout = timeout if timeout is not None else _env_int("C4NORM_VISION_TIMEOUT", 120)
        self.retries = retries
        self._chat = chat

    def extract(self, image_bytes: bytes, prompt: str = "", c4_level: int = 2) -> str:
        """
        Analiza la imagen y devuelve XML Draw.io crudo.

        Args:
            image_bytes: bytes de la imagen (PNG, JPEG o WebP).
            prompt: hint en lenguaje natural (se pasa al LLM como contexto).
            c4_level: nivel C4 objetivo; se incluye en el prompt al LLM.

        Returns:
            mxGraphModel XML listo para pasar a ``c4norm.normalize()``.
        """
        chat = self._chat if self._chat is not None else self._vision_chat
        if self._chat is None and not self.api_key:
            raise ValueError(
                "VisionExtractor requiere C4NORM_LLM_API_KEY (o inyectar 'chat'). "
                f"Modelo configurado: {self.model}."
            )

        level_label = _LEVEL_LABELS.get(c4_level, f"nivel {c4_level}")
        hint = f"\nHint del usuario: «{prompt}»" if prompt.strip() else ""
        user_msg = (
            f"Analiza este diagrama y conviértelo a XML draw.io "
            f"(el diagrama representa arquitectura a nivel C4 {c4_level} — {level_label}).{hint}"
        )

        last_exc: Exception | None = None
        for _attempt in range(self.retries + 1):
            raw = chat(image_bytes, user_msg)
            xml = _strip_fences(raw)
            if "<mxGraphModel" in xml or "<mxCell" in xml:
                return xml
            last_exc = ValueError(f"El LLM no produjo XML Draw.io: {xml[:200]!r}")
            user_msg += "\n\nIMPORTANTE: devuelve ÚNICAMENTE XML válido comenzando con <mxGraphModel>."
        raise ValueError(
            f"VisionExtractor: respuesta inválida tras {self.retries + 1} intentos: {last_exc}"
        )

    def _vision_chat(self, image_bytes: bytes, prompt: str) -> str:  # pragma: no cover
        import httpx

        b64 = base64.b64encode(image_bytes).decode("ascii")
        mime = _mime_type(image_bytes)
        try:
            response = httpx.post(
                f"{self.api_base.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": _VISION_SYSTEM},
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                                },
                                {"type": "text", "text": prompt},
                            ],
                        },
                    ],
                },
                timeout=self.timeout,
            )
        except httpx.RequestError as exc:
            raise ValueError(f"VisionExtractor: error de red al contactar {self.api_base}: {exc}") from exc
        if not response.is_success:
            raise ValueError(f"VisionExtractor: el proveedor devolvió {response.status_code}: {response.text[:300]}")
        return str(response.json()["choices"][0]["message"]["content"])
