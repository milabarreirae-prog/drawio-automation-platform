"""
Hoja de ingeniería: marco + cajetín ISO 7200 + hoja ajustada al contenido.

La página se dimensiona al dibujo (la abraza), manteniendo escala 1:1 y el mínimo
blanco sobrante, eligiendo orientación según el contenido. El cajetín reporta el
formato estándar (A4/A3/…) más cercano para comunicación. Ver
docs/C4_NORMALIZER_DESIGN.md §10.
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.sax.saxutils import escape

# Áreas de los formatos estándar (para reportar el más cercano en el cajetín).
_BASE_PORTRAIT: dict[str, tuple[int, int]] = {
    "A4": (827, 1169),
    "A3": (1169, 1654),
    "A2": (1654, 2339),
    "A1": (2339, 3308),
    "A0": (3308, 4677),
}
_ORDER = ["A4", "A3", "A2", "A1", "A0"]

# Formato objetivo de impresión y tope de ancho de página (en apaisado). El motor
# abraza el contenido 1:1 mientras quepa a lo ancho de este formato; superado el tope,
# deja de crecer horizontalmente y cede a la escala/multi-hoja (ver fit_page). Sin él,
# un boundary con decenas de hijos hermanos en fila producía una hoja A0++ correcta
# pero impresa a escala minúscula.
_TARGET_FMT = "A2"
_MAX_PAGE_W = max(_BASE_PORTRAIT[_TARGET_FMT])  # 2339 (A2 apaisado)

# Márgenes del marco (izquierda mayor, por encuadernación), padding y cajetín.
_M_LEFT, _M_OTHER, _PAD = 40, 25, 24
_TB_W, _TB_H = 540, 200


@dataclass
class TitleBlock:
    """Campos del cajetín ISO 7200."""

    project: str = "—"
    title: str = "—"
    doc_type: str = ""  # As-Is / To-Be / ...
    drawn_by: str = "—"
    approved_by: str = "—"  # revisó / arquitecto
    date: str = ""
    revision: str = "A"
    organization: str = ""   # propietario legal (ISO 7200)
    doc_number: str = ""     # número de plano / identificación del documento (ISO 7200)
    sheet_n: int = 1
    sheet_m: int = 1
    fmt: str = "A3"
    orientation: str = "landscape"
    scale: str = "1:1"


@dataclass
class DrawArea:
    x0: float
    y0: float
    width: float
    height: float


def _nearest_format(page_w: float, page_h: float) -> str:
    """Formato estándar (A*) más pequeño cuya área cubre la página, para el cajetín."""
    page_area = page_w * page_h
    for fmt in _ORDER:
        w, h = _BASE_PORTRAIT[fmt]
        if w * h >= page_area:
            return fmt
    return "A0"


def fit_page(content_w: float, content_h: float) -> tuple[int, int, DrawArea, str, str]:
    """Página ajustada al contenido (1:1, mínimo blanco) con ancho acotado al formato.

    Abraza el contenido 1:1 mientras quepa a lo ancho del formato objetivo (A2 apaisado).
    Superado ese tope, la página deja de crecer horizontalmente y el área de dibujo queda
    más estrecha que el contenido: `_fit` reduce entonces la escala (y, con ≥2 boundaries,
    el multi-hoja absorbe el resto) en vez de emitir una hoja A0++ impresa minúscula.

    Devuelve (page_w, page_h, draw_area, fmt_label, orientation).
    """
    cw, ch = max(1.0, content_w), max(1.0, content_h)
    frame_w = max(cw + 2 * _PAD, _TB_W + 2 * _PAD)
    page_w = int(_M_LEFT + frame_w + _M_OTHER)

    # Tope de ancho: no seguimos creciendo la hoja a lo ancho más allá del formato objetivo.
    if page_w > _MAX_PAGE_W:
        page_w = _MAX_PAGE_W
        frame_w = page_w - _M_LEFT - _M_OTHER

    frame_h = ch + 2 * _PAD + _TB_H
    page_h = int(_M_OTHER + frame_h + _M_OTHER)

    area = DrawArea(x0=_M_LEFT + _PAD, y0=_M_OTHER + _PAD, width=frame_w - 2 * _PAD, height=ch)
    orientation = "landscape" if page_w >= page_h else "portrait"
    return page_w, page_h, area, _nearest_format(page_w, page_h), orientation


def frame_rect(page_w: int, page_h: int) -> tuple[int, int, int, int]:
    return _M_LEFT, _M_OTHER, page_w - _M_LEFT - _M_OTHER, page_h - 2 * _M_OTHER


def scale_string(s: float) -> str:
    return "1:1" if s >= 0.999 else f"1:{1 / s:.1f}"


def _attr(value: str) -> str:
    return escape(value, {'"': "&quot;", "\n": "&#10;"})


def _cell(cid: str, value: str, style: str, x: float, y: float, w: float, h: float) -> str:
    return (
        f'        <mxCell id="{cid}" value="{_attr(value)}" style="{_attr(style)}" '
        f'parent="1" vertex="1">\n'
        f'          <mxGeometry x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" as="geometry" />\n'
        f"        </mxCell>"
    )


def render_frame_and_title_block(page_w: int, page_h: int, tb: TitleBlock) -> list[str]:
    """Devuelve las mxCell del marco + cajetín ISO 7200 para una página dada."""
    fx, fy, fw, fh = frame_rect(page_w, page_h)
    tbx, tby = fx + fw - _TB_W, fy + fh - _TB_H

    border = "rounded=0;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#000000;strokeWidth=2;"
    box = "rounded=0;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#000000;align=left;verticalAlign=middle;spacingLeft=6;fontSize=10;"
    box_title = box + "fontStyle=1;fontSize=12;"

    cells: list[str] = [_cell("c4norm-frame", "", border, fx, fy, fw, fh)]

    type_suffix = f"  [{tb.doc_type}]" if tb.doc_type else ""
    org_suffix = f" | <b>ORG:</b> {tb.organization}" if tb.organization else ""
    docno_suffix = f" | <b>N° plano:</b> {tb.doc_number}" if tb.doc_number else ""
    cells.append(_cell("c4norm-tb-proj", f"<b>PROYECTO:</b> {tb.project}{org_suffix}", box, tbx, tby, _TB_W, 36))
    cells.append(
        _cell("c4norm-tb-title", f"<b>TÍTULO:</b> {tb.title}{type_suffix}{docno_suffix}", box_title, tbx, tby + 36, _TB_W, 40)
    )

    gx, gy, gw, gh = tbx, tby + 76, _TB_W, _TB_H - 76
    cw, rh = gw / 2, gh / 3
    fields = [
        ("Dibujó", tb.drawn_by),
        ("Fecha", tb.date),
        ("Revisó / Arq.", tb.approved_by),
        ("Revisión", tb.revision),
        ("Escala", tb.scale),
        ("Hoja", f"{tb.sheet_n} de {tb.sheet_m} · ≈{tb.fmt} {tb.orientation[:4]}."),
    ]
    for i, (label, value) in enumerate(fields):
        r, c = divmod(i, 2)
        cells.append(
            _cell(f"c4norm-tb-f{i}", f"<b>{label}</b><br>{escape(value)}", box, gx + c * cw, gy + r * rh, cw, rh)
        )
    return cells
