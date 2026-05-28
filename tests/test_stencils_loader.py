"""
Tests for stencil loading and resolution (worker/stencils_loader.py).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from worker.models import DegradationMode, StencilResolutionResult
from worker.stencils_loader import (
    StencilResolutionPolicy,
    StencilsLoader,
    inject_mxlibrary,
)


# =============================================================================
# Helpers
# =============================================================================


@pytest.fixture
def temp_manifest_dir(tmp_path: Path, monkeypatch) -> Path:
    """Create a temporary manifest and stencil cache directory for testing."""
    manifest = {
        "version": "1.0.0",
        "stencils": {
            "aws4": {
                "name": "AWS",
                "type": "url",
                "lib_param": "Uhttps://libs.example.com/aws4.xml",
                "license": "Proprietary",
                "commercial_use": "allowed_with_attribution",
                "requires_license_key": False,
                "source_url": "https://libs.example.com/aws4.xml",
            },
            "archimate3": {
                "name": "ArchiMate",
                "type": "url",
                "lib_param": "Uhttps://libs.example.com/archimate3.xml",
                "license": "Proprietary (The Open Group)",
                "commercial_use": "requires_license",
                "requires_license_key": True,
                "license_env_var": "ARCHIMATE_LICENSE_KEY",
                "source_url": "https://libs.example.com/archimate3.xml",
            },
            "gcp2": {
                "name": "GCP",
                "type": "url",
                "lib_param": "Uhttps://libs.example.com/gcp2.xml",
                "license": "CC BY 4.0",
                "commercial_use": "allowed_with_attribution",
                "requires_license_key": False,
                "source_url": "https://libs.example.com/gcp2.xml",
            },
            "leanix": {
                "name": "LeanIX",
                "type": "unavailable",
                "license": "Proprietary",
                "commercial_use": "unavailable",
                "requires_license_key": True,
            },
        },
    }
    manifest_path = tmp_path / "stencils" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest))

    download_dir = tmp_path / "stencils" / "downloaded"
    download_dir.mkdir(parents=True, exist_ok=True)

    # Patch constants
    monkeypatch.setattr("worker.stencils_loader.MANIFEST_PATH", manifest_path)
    monkeypatch.setattr("worker.stencils_loader.DOWNLOAD_DIR", download_dir)

    return tmp_path


# =============================================================================
# StencilResolutionPolicy Tests
# =============================================================================


class TestStencilResolutionPolicy:
    """Tests for the stencil resolution decision matrix."""

    def test_resolve_allowed_cached_stencil(self, temp_manifest_dir: Path) -> None:
        policy = StencilResolutionPolicy(allowed_stencils=["aws4"], archimate_license=False)
        result = policy.resolve(["aws4"])
        assert result.success is True
        assert "aws4" in result.resolved_stencils or result.libraries_param

    def test_resolve_archimate_no_license_blocks(self, temp_manifest_dir: Path) -> None:
        policy = StencilResolutionPolicy(allowed_stencils=["archimate3"], archimate_license=False)
        result = policy.resolve(["archimate3"])
        assert result.success is False
        assert any("ArchiMate" in w for w in result.warnings)

    def test_resolve_archimate_with_license(self, temp_manifest_dir: Path) -> None:
        policy = StencilResolutionPolicy(allowed_stencils=["archimate3"], archimate_license=True)
        result = policy.resolve(["archimate3"])
        # Should not be blocked, but may warn about caching
        assert result.success is True

    def test_resolve_disallowed_stencil(self, temp_manifest_dir: Path) -> None:
        policy = StencilResolutionPolicy(allowed_stencils=["gcp2"], archimate_license=False)
        result = policy.resolve(["aws4"])
        assert result.success is False
        assert any("not in allowed" in w for w in result.warnings)

    def test_resolve_unavailable_stencil(self, temp_manifest_dir: Path) -> None:
        policy = StencilResolutionPolicy(allowed_stencils=["leanix"], archimate_license=False)
        result = policy.resolve(["leanix"])
        assert result.success is False
        assert any("unavailable" in w.lower() for w in result.warnings)

    def test_resolve_multiple_stencils(self, temp_manifest_dir: Path) -> None:
        policy = StencilResolutionPolicy(allowed_stencils=["aws4", "gcp2"], archimate_license=False)
        result = policy.resolve(["aws4", "gcp2"])
        assert result.success is True
        assert len(result.missing_stencils) == 0

    def test_resolve_mixed_allowed_and_blocked(self, temp_manifest_dir: Path) -> None:
        policy = StencilResolutionPolicy(allowed_stencils=["aws4"], archimate_license=False)
        result = policy.resolve(["aws4", "leanix"])
        # aws4 OK, leanix blocked
        assert "aws4" in result.resolved_stencils or result.libraries_param
        assert "leanix" in result.missing_stencils
        assert result.success is False

    def test_empty_stencil_list(self, temp_manifest_dir: Path) -> None:
        policy = StencilResolutionPolicy()
        result = policy.resolve([])
        assert result.success is True
        assert result.degradation_mode == DegradationMode.NONE

    def test_cached_stencil_used(self, temp_manifest_dir: Path) -> None:
        """When a stencil XML file is cached, it should be used."""
        from worker.stencils_loader import DOWNLOAD_DIR
        cached = DOWNLOAD_DIR / "aws4.xml"
        cached.write_text("<shapes/>")

        policy = StencilResolutionPolicy(allowed_stencils=["aws4"])
        result = policy.resolve(["aws4"])
        assert result.success is True
        # Should find the cached file
        assert result.libraries_param

    def test_libraries_param_format(self, temp_manifest_dir: Path) -> None:
        policy = StencilResolutionPolicy(allowed_stencils=["aws4", "gcp2"])
        result = policy.resolve(["aws4", "gcp2"])
        assert result.libraries_param
        assert "Uhttps://" in result.libraries_param


# =============================================================================
# mxLibrary Injection Tests
# =============================================================================


class TestMxLibraryInjection:
    """Tests for mxLibrary injection into Draw.io XML."""

    def test_inject_single_library(self) -> None:
        xml = """<mxGraphModel><root><mxCell id="0"/></root></mxGraphModel>"""
        result = inject_mxlibrary(xml, ["https://libs.example.com/aws4.xml"])
        assert "mxLibrary" in result

    def test_inject_multiple_libraries(self) -> None:
        xml = """<mxGraphModel><root><mxCell id="0"/></root></mxGraphModel>"""
        result = inject_mxlibrary(xml, [
            "https://libs.example.com/aws4.xml",
            "https://libs.example.com/gcp2.xml",
        ])
        assert result.count("mxLibrary") >= 2

    def test_no_duplicate_injection(self) -> None:
        xml = """<mxGraphModel><root><mxCell id="0"/><mxLibrary name="https://libs.example.com/aws4.xml"/></root></mxGraphModel>"""
        result = inject_mxlibrary(xml, ["https://libs.example.com/aws4.xml"])
        # Should only have one mxLibrary (the existing one)
        assert result.count("mxLibrary") <= 1

    def test_empty_libraries_no_change(self) -> None:
        xml = """<mxGraphModel><root><mxCell id="0"/></root></mxGraphModel>"""
        result = inject_mxlibrary(xml, [])
        assert result == xml

    def test_malformed_xml_returns_original(self) -> None:
        xml = """<not><valid<<<xml"""
        result = inject_mxlibrary(xml, ["https://libs.example.com/aws4.xml"])
        assert result == xml  # Should return unchanged


# =============================================================================
# StencilsLoader Tests
# =============================================================================


class TestStencilsLoader:
    """Tests for the high-level StencilsLoader."""

    def test_process_compliant_xml(self, temp_manifest_dir: Path, valid_xml_basic: str) -> None:
        loader = StencilsLoader(allowed_stencils=["aws4", "gcp2"])
        result = loader.process_xml_with_fallback(valid_xml_basic)
        assert result.success is True

    def test_process_with_archimate_no_license(self, temp_manifest_dir: Path, valid_xml_with_archimate: str) -> None:
        loader = StencilsLoader(allowed_stencils=["archimate3"], archimate_license=False)
        result = loader.process_xml_with_fallback(valid_xml_with_archimate, required_stencils=["archimate3"])
        assert result.success is False
        assert any("ArchiMate" in w for w in result.warnings)

    def test_xml_enriched_when_libraries_present(self, temp_manifest_dir: Path) -> None:
        from worker.stencils_loader import DOWNLOAD_DIR
        # Cache AWS stencil
        cached = DOWNLOAD_DIR / "aws4.xml"
        cached.write_text("<shapes/>")

        xml = """<mxGraphModel><root><mxCell id="0"/></root></mxGraphModel>"""
        loader = StencilsLoader(allowed_stencils=["aws4"])
        result = loader.process_xml_with_fallback(xml, required_stencils=["aws4"])
        assert result.xml_enriched
        # Should have injected mxLibrary
        if result.libraries_param:
            assert "mxLibrary" in result.xml_enriched

    def test_degradation_mode_tracked(self, temp_manifest_dir: Path) -> None:
        """When stencils are missing/blocked, degradation mode should reflect that."""
        loader = StencilsLoader(allowed_stencils=["gcp2"])
        xml = """<mxGraphModel><root><mxCell id="0"/></root></mxGraphModel>"""
        result = loader.process_xml_with_fallback(xml, required_stencils=["aws4"])
        assert result.degradation_mode != DegradationMode.NONE
        assert "aws4" in result.missing_stencils