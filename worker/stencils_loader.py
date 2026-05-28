"""
Stencil Resolution and Loading for the Rendering Worker.

Implements a decision matrix that determines how to handle stencil libraries
when rendering Draw.io diagrams:

Decision Matrix:
  1. BLOCKED by policy/license → Reject rendering
  2. Cached locally → Use cached version
  3. Placeholder if offline/cache miss → Use basic shapes
  4. Download with exponential backoff → Fetch from source URL

Also handles <mxLibrary> injection into XML for draw.io CLI.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from lxml import etree

from worker.models import DegradationMode, StencilResolutionResult

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

MANIFEST_PATH = Path("stencils/manifest.json")
DOWNLOAD_DIR = Path("stencils/downloaded")
MXGRAPHML_NAMESPACE = "http://www.w3.org/1999/xhtml"


# =============================================================================
# Stencil Resolution Policy
# =============================================================================


class StencilResolutionPolicy:
    """
    Decision matrix for stencil resolution.

    Determines whether to use cached stencils, fetch from source,
    fall back to placeholders, or block rendering entirely.

    Matrix:
        License OK + Cached → Use cached
        License OK + Not cached → Download (with backoff)
        License OK + Offline + Not cached → Placeholder
        License BLOCKED (ArchiMate no key) → BLOCK
        License BLOCKED (policy violation) → BLOCK
        Stencil unavailable (leanix) → BLOCK
    """

    def __init__(self, allowed_stencils: Optional[list[str]] = None, archimate_license: bool = False):
        self.allowed_stencils = set(allowed_stencils or [])
        self.archimate_license = archimate_license
        self._manifest: Optional[dict] = None

    # -------------------------------------------------------------------------
    # Manifest Loading
    # -------------------------------------------------------------------------

    def _load_manifest(self) -> dict:
        """Lazy-load the stencil manifest."""
        if self._manifest is None:
            if not MANIFEST_PATH.exists():
                logger.warning("Stencil manifest not found at %s", MANIFEST_PATH)
                self._manifest = {"stencils": {}}
            else:
                with open(MANIFEST_PATH, encoding="utf-8") as f:
                    self._manifest = json.load(f)
                logger.debug("Loaded stencil manifest: %d stencils", len(self._manifest.get("stencils", {})))
        return self._manifest

    # -------------------------------------------------------------------------
    # Single Stencil Resolution
    # -------------------------------------------------------------------------

    def _resolve_stencil(self, stencil_id: str) -> tuple[str | None, str | None, list[str]]:
        """
        Resolve a single stencil.

        Returns:
            Tuple of (lib_param or None, degradation_warning or None, list of warnings).
        """
        manifest = self._load_manifest()
        stencils = manifest.get("stencils", {})

        if stencil_id not in stencils:
            return None, f"Unknown stencil '{stencil_id}' — skipping", []

        entry = stencils[stencil_id]

        # Check: Is the stencil unavailable?
        if entry.get("type") == "unavailable":
            return None, f"Stencil '{stencil_id}' is marked as unavailable", []

        # Check: Does this stencil require a license key?
        if entry.get("requires_license_key") and entry.get("license_env_var") == "ARCHIMATE_LICENSE_KEY":
            if not self.archimate_license:
                return None, f"ArchiMate license required but not configured — BLOCKING", []

        # Check: Is this stencil allowed by policy?
        if self.allowed_stencils and stencil_id not in self.allowed_stencils:
            return None, f"Stencil '{stencil_id}' is not in allowed stencils list", []

        # Check: Is the stencil cached locally?
        cached_path = DOWNLOAD_DIR / f"{stencil_id}.xml"
        if cached_path.exists():
            logger.debug("Using cached stencil: %s (%s)", stencil_id, cached_path)
            return entry.get("lib_param"), None, []

        # Check: Do we have a source URL to download from?
        source_url = entry.get("source_url")
        if source_url:
            return entry.get("lib_param"), None, [f"Stencil '{stencil_id}' will be fetched from source at runtime"]

        # Fallback: No cache, no source — use placeholder
        return None, None, [f"Stencil '{stencil_id}' not cached and no source URL — will use placeholder"]

    # -------------------------------------------------------------------------
    # Batch Resolution
    # -------------------------------------------------------------------------

    def resolve(self, required_stencils: list[str]) -> StencilResolutionResult:
        """
        Resolve all required stencils and produce the libraries parameter.

        Args:
            required_stencils: List of stencil IDs to resolve.

        Returns:
            StencilResolutionResult with libraries param, degradation info, and warnings.
        """
        if not required_stencils:
            return StencilResolutionResult()

        lib_params: list[str] = []
        blocked: list[str] = []
        warnings: list[str] = []
        resolved: list[str] = []
        missing: list[str] = []

        for stencil_id in required_stencils:
            lib_param, block_reason, stencil_warnings = self._resolve_stencil(stencil_id)
            warnings.extend(stencil_warnings)

            if block_reason:
                blocked.append(f"{stencil_id}: {block_reason}")
                missing.append(stencil_id)
                continue

            if lib_param:
                lib_params.append(lib_param)
                resolved.append(stencil_id)
            else:
                missing.append(stencil_id)

        # Build libraries parameter
        libraries_param = " ".join(lib_params) if lib_params else ""

        # Determine degradation mode
        if blocked:
            # Check if any blocked stencil is a BLOCKING issue (license required)
            has_license_block = any("ArchiMate" in b for b in blocked)
            has_policy_block = any("not in allowed" in b for b in blocked)
            has_unavailable_block = any("unavailable" in b.lower() for b in blocked)

            if has_license_block:
                return StencilResolutionResult(
                    success=False,
                    degradation_mode=DegradationMode.STENCIL_STRIPPED,
                    resolved_stencils=resolved,
                    missing_stencils=missing,
                    warnings=warnings + blocked,
                )
            elif has_policy_block:
                return StencilResolutionResult(
                    success=False,
                    degradation_mode=DegradationMode.STENCIL_STRIPPED,
                    resolved_stencils=resolved,
                    missing_stencils=missing,
                    warnings=warnings + blocked,
                )
            elif has_unavailable_block:
                return StencilResolutionResult(
                    success=False,
                    degradation_mode=DegradationMode.STENCIL_STRIPPED,
                    resolved_stencils=resolved,
                    missing_stencils=missing,
                    warnings=warnings + blocked,
                )

        if missing:
            return StencilResolutionResult(
                success=True,
                libraries_param=libraries_param,
                degradation_mode=DegradationMode.PLACEHOLDER,
                resolved_stencils=resolved,
                missing_stencils=missing,
                warnings=warnings,
            )

        return StencilResolutionResult(
            success=True,
            libraries_param=libraries_param,
            resolved_stencils=resolved,
            warnings=warnings,
        )


# =============================================================================
# XML Enrichment (mxLibrary Injection)
# =============================================================================


def inject_mxlibrary(xml_content: str, libraries: list[str]) -> str:
    """
    Inject <mxLibrary> elements into Draw.io XML for stencil resolution.

    Draw.io CLI expects <mxLibrary> elements in the XML to load
    external stencil libraries. This function adds them if missing.

    Args:
        xml_content: Original Draw.io XML string.
        libraries: List of lib_param values to inject.

    Returns:
        XML string with <mxLibrary> elements added.
    """
    if not libraries:
        return xml_content

    try:
        parser = etree.XMLParser(recover=False, remove_blank_text=True)
        root = etree.fromstring(xml_content.encode("utf-8"), parser=parser)
    except etree.XMLSyntaxError:
        logger.warning("Could not parse XML for library injection — using raw XML")
        return xml_content

    # Check if mxLibrary already exists
    existing_libs: set[str] = set()
    for lib_elem in root.iter(f"{{{MXGRAPHML_NAMESPACE}}}mxLibrary"):
        name = lib_elem.get("name", "")
        existing_libs.add(name)
    for lib_elem in root.iter("mxLibrary"):
        name = lib_elem.get("name", "")
        existing_libs.add(name)

    # Add missing libraries
    added = 0
    for lib_param in libraries:
        lib_name = lib_param[1:] if lib_param.startswith("U") else lib_param
        if lib_name not in existing_libs:
            lib_elem = etree.SubElement(root, "mxLibrary")
            lib_elem.set("name", lib_name)
            existing_libs.add(lib_name)
            added += 1
            logger.debug("Injected mxLibrary: %s", lib_name)

    if added > 0:
        result = etree.tostring(root, encoding="unicode", pretty_print=True)
        logger.info("Injected %d mxLibrary element(s) into XML", added)
        return result

    return xml_content


# =============================================================================
# High-Level StencilsLoader
# =============================================================================


class StencilsLoader:
    """
    High-level API for loading and resolving stencils in a rendering task.

    Combines StencilResolutionPolicy with XML enrichment.

    Usage:
        loader = StencilsLoader(allowed_stencils, archimate_license)
        result = loader.process_xml_with_fallback(xml_content, export_format)
    """

    def __init__(self, allowed_stencils: Optional[list[str]] = None, archimate_license: bool = False):
        self.policy = StencilResolutionPolicy(allowed_stencils, archimate_license)

    def process_xml_with_fallback(
        self,
        xml_content: str,
        required_stencils: Optional[list[str]] = None,
    ) -> StencilResolutionResult:
        """
        Process XML with stencil resolution and fallback strategy.

        If stencil resolution fails (BLOCKED), the result will
        indicate degradation and the caller should handle accordingly.

        Args:
            xml_content: Raw Draw.io XML content.
            required_stencils: List of stencil IDs needed. If None, auto-detect.

        Returns:
            StencilResolutionResult with enriched XML and libraries parameter.
        """
        # Resolve stencils using the decision matrix
        result = self.policy.resolve(required_stencils or [])

        # If blocked, return immediately — caller should abort rendering
        if not result.success:
            logger.warning("Stencil resolution BLOCKED: %s", result.warnings)
            return result

        # Inject mxLibrary elements into XML if we have libraries
        if result.libraries_param:
            # Extract URLs from libraries_param
            lib_urls = [p[1:] for p in result.libraries_param.split() if p.startswith("U")]
            try:
                enriched_xml = inject_mxlibrary(xml_content, lib_urls)
                result.xml_enriched = enriched_xml
            except Exception as e:
                logger.warning("Failed to inject mxLibrary: %s — using original XML", e)
                result.xml_enriched = xml_content
                result.warnings.append(f"mxLibrary injection failed: {e}")
        else:
            result.xml_enriched = xml_content

        return result