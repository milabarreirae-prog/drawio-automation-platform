"""
XML Linting and Corporate Compliance Validator.

Uses lxml to parse Draw.io XML and validate:
1. XML well-formedness
2. Color palette compliance (ALLOWED_COLORS)
3. Stencil library compliance (ALLOWED_STENCILS)
4. ArchiMate license requirement (ARCHIMATE_LICENSE_KEY)

Raises ValueError with structured details on policy violations.
"""

from __future__ import annotations

import re

from lxml import etree

from api.config import Settings, get_settings
from api.schemas import ColorViolation, ComplianceCheck, ComplianceLevel, StencilViolation

# =============================================================================
# Constants
# =============================================================================

# XML namespace for mxGraphModel
MX_NAMESPACES = {
    "mx": "http://www.w3.org/1999/xhtml",
}

# Color attributes to scan in Draw.io XML
COLOR_ATTRIBUTES = frozenset({
    "fillColor",
    "strokeColor",
    "fontColor",
    "gradientColor",
    "labelBackgroundColor",
    "labelBorderColor",
    "swimlaneFillColor",
})

# Known color patterns
HEX_COLOR_PATTERN = re.compile(r"^#?([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})$")
DEFAULT_COLORS = frozenset({"none", "default", "inherit", "transparent", "", "#ffffff", "#FFFFFF", "#000000", "#000"})

# Stencil detection patterns in mxCell style attribute
STENCIL_PATTERN = re.compile(r"shape=([^;]+)")
SHAPE_PATTERNS = {
    "aws4": re.compile(r"(aws|amazon|aws4)", re.IGNORECASE),
    "gcp2": re.compile(r"(gcp|google|gcp2)", re.IGNORECASE),
    "azure": re.compile(r"(azure|microsoft)", re.IGNORECASE),
    "archimate3": re.compile(r"(archimate|archi)", re.IGNORECASE),
    "c4": re.compile(r"(c4|structurizr|container|system)", re.IGNORECASE),
    "cisco": re.compile(r"(cisco|network)", re.IGNORECASE),
    "oci": re.compile(r"(oci|oracle)", re.IGNORECASE),
    "leanix": re.compile(r"leanix", re.IGNORECASE),
}

# Combined pattern to detect any stencil shape match
ANY_STENCIL_PATTERN = re.compile(
    r"(aws|amazon|gcp|google|azure|microsoft|archimate|archi|c4|structurizr|cisco|network|oci|oracle|leanix)",
    re.IGNORECASE,
)


# =============================================================================
# XML Well-Formedness Validation
# =============================================================================


def validate_xml_wellformed(xml_content: str) -> etree._Element:
    """
    Validate that the XML content is well-formed and parseable.

    Args:
        xml_content: Raw XML string.

    Returns:
        Parsed XML element tree root.

    Raises:
        ValueError: If XML is malformed.
    """
    if not xml_content or not xml_content.strip():
        raise ValueError("XML content is empty")

    try:
        parser = etree.XMLParser(recover=False, resolve_entities=False, no_network=True, load_dtd=False)
        root = etree.fromstring(xml_content.encode("utf-8"), parser=parser)
    except etree.XMLSyntaxError as e:
        raise ValueError(f"Malformed XML: {e}") from e
    except etree.DocumentInvalid as e:
        raise ValueError(f"Invalid XML document: {e}") from e
    except Exception as e:
        raise ValueError(f"XML parsing error: {e}") from e

    return root


# =============================================================================
# Color Extraction and Validation
# =============================================================================


def extract_colors(root: etree._Element) -> dict[str, list[tuple[str, str]]]:
    """
    Extract all color values from mxCell elements in the XML.

    Returns:
        Dict mapping color hex values to list of (attribute_name, element_id) tuples.
    """
    colors: dict[str, list[tuple[str, str]]] = {}

    for cell in root.iter("mxCell"):
        style = cell.get("style", "")
        element_id = cell.get("id", "unknown")

        if not style:
            continue

        # Parse style attributes (semicolon-separated key=value pairs)
        for attr in style.split(";"):
            attr = attr.strip()
            if "=" not in attr:
                continue

            key, _, value = attr.partition("=")
            key = key.strip()
            value = value.strip()

            if key not in COLOR_ATTRIBUTES:
                continue

            # Skip non-color values
            if value.lower() in DEFAULT_COLORS:
                continue

            # Normalize hex color
            if HEX_COLOR_PATTERN.match(value.lstrip("#")):
                normalized = value.lstrip("#").upper()
                if normalized not in colors:
                    colors[normalized] = []
                colors[normalized].append((key, element_id))

    return colors


def validate_colors(
    extracted_colors: dict[str, list[tuple[str, str]]],
    allowed_colors: list[str],
) -> list[ColorViolation]:
    """
    Validate colors against the allowed palette.

    Args:
        extracted_colors: Colors extracted from XML.
        allowed_colors: List of allowed hex colors (uppercase, no #).

    Returns:
        List of ColorViolation objects for disallowed colors.
    """
    if not allowed_colors:
        return []  # Color validation disabled

    allowed_set = set(allowed_colors)
    violations: list[ColorViolation] = []

    for color_hex, occurrences in extracted_colors.items():
        if color_hex not in allowed_set:
            for attr_name, element_id in occurrences:
                violations.append(ColorViolation(
                    color_hex=f"#{color_hex}",
                    attribute_name=attr_name,
                    element_id=element_id,
                ))

    return violations


# =============================================================================
# Stencil Detection and Validation
# =============================================================================


def detect_stencils(root: etree._Element) -> set[str]:
    """
    Detect which stencil libraries are referenced in the XML.

    Scans mxCell style attributes for known stencil shape patterns.

    Returns:
        Set of detected stencil IDs.
    """
    detected: set[str] = set()

    for cell in root.iter("mxCell"):
        style = cell.get("style", "")

        if not style:
            continue

        for stencil_id, pattern in SHAPE_PATTERNS.items():
            if pattern.search(style):
                detected.add(stencil_id)

    return detected


def detect_unrecognized_stencils(root: etree._Element) -> set[str]:
    """
    Detect explicit `shape=` tokens whose value maps to NO known stencil family.

    Fail-closed contra el antipatrón allowlist-por-omisión (Ax-C4N-016 /
    gates_fail_closed): `detect_stencils()` sólo ve las 8 familias de
    `SHAPE_PATTERNS`; un stencil corporativo no listado (p.ej. `shape=sap.hana.node`)
    quedaba invisible y el diagrama heredaba "conforme" en silencio. Aquí se
    inspecciona el valor del propio token `shape=` — no el estilo entero, para no
    confundir un match de familia que ocurra en otro atributo — y todo lo que no
    reconozca ninguna familia se devuelve como "por validar". El motor no lo declara
    violación (no inventa lo que no puede probar) pero tampoco lo deja pasar mudo.

    Returns:
        Set of raw `shape=` values that matched no known family.
    """
    unrecognized: set[str] = set()

    for cell in root.iter("mxCell"):
        style = cell.get("style", "")

        if not style:
            continue

        for match in STENCIL_PATTERN.finditer(style):
            shape_value = match.group(1).strip()
            if not shape_value:
                continue
            if not ANY_STENCIL_PATTERN.search(shape_value):
                unrecognized.add(shape_value)

    return unrecognized


def validate_stencils(
    detected_stencils: set[str],
    allowed_stencils: list[str],
) -> list[StencilViolation]:
    """
    Validate detected stencils against the allowed list.

    Args:
        detected_stencils: Stencil IDs found in the XML.
        allowed_stencils: List of allowed stencil IDs.

    Returns:
        List of StencilViolation objects for disallowed stencils.
    """
    if not allowed_stencils:
        return []  # No stencil filtering configured

    allowed_set = set(allowed_stencils)
    violations: list[StencilViolation] = []

    for stencil_id in detected_stencils:
        if stencil_id not in allowed_set:
            violations.append(StencilViolation(stencil_id=stencil_id))

    return violations


# =============================================================================
# ArchiMate License Check
# =============================================================================


def requires_archimate_license(detected_stencils: set[str]) -> bool:
    """Check if ArchiMate stencils are detected in the XML."""
    return "archimate3" in detected_stencils


# =============================================================================
# Full Validation (Orchestrator)
# =============================================================================


class XMLLinter:
    """
    Orchestrates the full compliance validation pipeline.

    Usage:
        linter = XMLLinter(settings)
        result = linter.full_validation(xml_content)
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def full_validation(self, xml_content: str) -> ComplianceCheck:
        """
        Run the complete compliance validation pipeline.

        Steps:
        1. Verify XML well-formedness
        2. Extract and validate colors
        3. Detect and validate stencils
        4. Check ArchiMate license requirement

        Returns:
            ComplianceCheck with full validation results.
        """
        errors: list[str] = []
        color_violations: list[ColorViolation] = []
        stencil_violations: list[StencilViolation] = []
        detected_stencils: set[str] = set()
        unrecognized_stencils: set[str] = set()
        xml_well_formed = True
        archimate_needed = False
        archimate_valid = False

        # Step 1: XML well-formedness
        try:
            root = validate_xml_wellformed(xml_content)
        except ValueError as e:
            xml_well_formed = False
            errors.append(str(e))
            return ComplianceCheck(
                level=ComplianceLevel.BLOCKED,
                xml_well_formed=False,
                errors=errors,
            )

        # Step 2: Color validation
        if self.settings.is_color_validation_enabled:
            try:
                extracted_colors = extract_colors(root)
                color_violations = validate_colors(
                    extracted_colors,
                    self.settings.allowed_colors_list,
                )
                if color_violations:
                    errors.append(f"Found {len(color_violations)} color violation(s)")
            except Exception as e:
                errors.append(f"Color validation error: {e}")

        # Step 3: Stencil validation
        detected_stencils = detect_stencils(root)
        if self.settings.allowed_stencils_list:
            try:
                stencil_violations = validate_stencils(
                    detected_stencils,
                    self.settings.allowed_stencils_list,
                )
                if stencil_violations:
                    errors.append(f"Found {len(stencil_violations)} stencil violation(s)")
            except Exception as e:
                errors.append(f"Stencil validation error: {e}")

        # Step 3b: Stencils no reconocidos (fail-closed, "por validar").
        # Un `shape=` que no mapea a ninguna familia conocida no se declara
        # violación (el motor no inventa) pero tampoco hereda "conforme" en
        # silencio: se marca por validar y eleva el nivel a WARNING.
        unrecognized_stencils = detect_unrecognized_stencils(root)
        if unrecognized_stencils:
            errors.append(
                f"Found {len(unrecognized_stencils)} unrecognized stencil(s) "
                f"(por validar): {', '.join(sorted(unrecognized_stencils))}"
            )

        # Step 4: ArchiMate license check
        archimate_needed = requires_archimate_license(detected_stencils)
        if archimate_needed:
            archimate_valid = self.settings.has_archimate_license
            if not archimate_valid:
                errors.append(
                    "ArchiMate stencils detected but no valid ARCHIMATE_LICENSE_KEY is configured. "
                    "ArchiMate is a registered trademark of The Open Group. "
                    "Commercial use requires a license: https://www.opengroup.org/certifications/archimate"
                )

        # Determine compliance level
        if not xml_well_formed or (color_violations or stencil_violations) or (archimate_needed and not archimate_valid):
            level = ComplianceLevel.BLOCKED
        elif errors:
            level = ComplianceLevel.WARNING
        else:
            level = ComplianceLevel.COMPLIANT

        return ComplianceCheck(
            level=level,
            xml_well_formed=xml_well_formed,
            stencils_detected=sorted(detected_stencils),
            unrecognized_stencils=sorted(unrecognized_stencils),
            stencil_violations=stencil_violations,
            color_violations=color_violations,
            requires_archimate_license=archimate_needed,
            archimate_license_valid=archimate_valid,
            errors=errors,
        )
