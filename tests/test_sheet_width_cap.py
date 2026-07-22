"""
B-14 — ancho de página acotado al formato objetivo.

`fit_page` abraza el contenido 1:1 mientras quepa a lo ancho del formato objetivo
(A2 apaisado). Superado ese tope, la hoja deja de crecer horizontalmente y el área de
dibujo queda MÁS ESTRECHA que el contenido: esa razón `area.width / content_w < 1` es
exactamente el factor que `_fit`/`_scale_only` traducen en reducción de escala (y, con
≥2 boundaries, en multi-hoja). Sin el tope, un boundary con decenas de hijos hermanos en
fila producía una hoja A0++ correcta pero impresa a escala minúscula.

Dientes deterministas sobre el mecanismo (no dependen del motor de layout): mutar la
cláusula del tope en `fit_page` deja rojo `test_wide_content_caps_page_width_at_target`.
"""

from __future__ import annotations

from c4norm.sheet import _MAX_PAGE_W, fit_page


def test_narrow_content_embraced_one_to_one() -> None:
    # Contenido que cabe holgado: la hoja NO se topa y el área abraza el contenido 1:1.
    content_w = 800.0
    page_w, _, area, _, _ = fit_page(content_w, 600.0)
    assert page_w < _MAX_PAGE_W
    assert area.width >= content_w  # cabe entero, sin necesidad de escalar


def test_wide_content_caps_page_width_at_target() -> None:
    # Fila de decenas de hermanos: mucho más ancha que A2.
    content_w = 12_000.0
    page_w, _, area, fmt, _ = fit_page(content_w, 600.0)
    assert page_w == _MAX_PAGE_W  # topado al formato objetivo, no A0++ desbocado
    # El área de dibujo queda más estrecha que el contenido -> _fit tendrá que escalar.
    assert area.width < content_w
    # Y el cajetín deja de reportar un formato mayor por ancho desbocado.
    assert fmt in {"A4", "A3", "A2"}


def test_cap_engages_scaling_below_one_to_one() -> None:
    # La razón area.width/content_w < 1 es el factor de reducción que consume _scale_only.
    content_w = 12_000.0
    _, _, area, _, _ = fit_page(content_w, 600.0)
    assert area.width / content_w < 1.0


def test_cap_is_flat_beyond_the_threshold() -> None:
    # Dos contenidos, ambos por encima del tope: el área NO sigue creciendo (queda plana).
    page_a, _, area_a, _, _ = fit_page(float(_MAX_PAGE_W + 4_000), 600.0)
    page_b, _, area_b, _, _ = fit_page(float(_MAX_PAGE_W + 40_000), 600.0)
    assert page_a == page_b == _MAX_PAGE_W
    assert area_a.width == area_b.width  # topado: más ancho de contenido no ensancha la hoja
