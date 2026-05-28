"""
Tests for XML linting and compliance validation (api/linting.py).
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from api.config import Settings
from api.linting import (
    XMLLinter,
    detect_stencils,
    extract_colors,
    requires_archimate_license,
    validate_colors,
    validate_stencils,
    validate_xml_wellformed,
)
from api.schemas import ComplianceLevel


class TestXMLWellFormedness:
    """Tests for XML well-formedness validation."""

    def test_valid_xml_parses(self, valid_xml_basic: str) -> None:
        root = validate_xml_wellformed(valid_xml_basic)
        assert root is not None
        assert root.tag == "mxGraphModel"

    def test_valid_xml_with_stencils(self, valid_xml_with_aws: str) -> None:
        root = validate_xml_wellformed(valid_xml_with_aws)
        assert root is not None

    def test_invalid_xml_raises(self, invalid_xml: str) -> None:
        with pytest.raises(ValueError, match="Malformed XML"):
            validate_xml_wellformed(invalid_xml)

    def test_empty_xml_raises(self, empty_xml: str) -> None:
        with pytest.raises(ValueError, match="empty"):
            validate_xml_wellformed(empty_xml)


class TestColorExtraction:
    """Tests for color extraction from XML."""

    def test_extract_colors_from_basic_xml(self, valid_xml_basic: str) -> None:
        root = validate_xml_wellformed(valid_xml_basic)
        colors = extract_colors(root)
        assert "4A90D9" in colors
        assert "333333" in colors
        assert "1A1A1A" in colors

    def test_extract_colors_no_colors(self) -> None:
        xml = """<mxGraphModel><root><mxCell id="0"/></root></mxGraphModel>"""
        root = validate_xml_wellformed(xml)
        assert extract_colors(root) == {}


class TestColorValidation:
    """Tests for color policy validation."""

    def test_allowed_colors_pass(self, valid_xml_basic: str) -> None:
        allowed = ["4A90D9", "333333", "1A1A1A"]
        root = validate_xml_wellformed(valid_xml_basic)
        colors = extract_colors(root)
        violations = validate_colors(colors, allowed)
        assert len(violations) == 0

    def test_disallowed_color_violation(self, valid_xml_with_disallowed_color: str) -> None:
        allowed = ["333333"]
        root = validate_xml_wellformed(valid_xml_with_disallowed_color)
        colors = extract_colors(root)
        violations = validate_colors(colors, allowed)
        assert len(violations) >= 1
        assert any(v.color_hex == "#FF0000" for v in violations)

    def test_empty_allowed_colors_disables_validation(self, valid_xml_basic: str) -> None:
        root = validate_xml_wellformed(valid_xml_basic)
        colors = extract_colors(root)
        violations = validate_colors(colors, [])
        assert len(violations) == 0


class TestStencilDetection:
    """Tests for stencil detection in XML."""

    def test_detect_aws_stencil(self, valid_xml_with_aws: str) -> None:
        root = validate_xml_wellformed(valid_xml_with_aws)
        detected = detect_stencils(root)
        assert "aws4" in detected

    def test_detect_archimate_stencil(self, valid_xml_with_archimate: str) -> None:
        root = validate_xml_wellformed(valid_xml_with_archimate)
        detected = detect_stencils(root)
        assert "archimate3" in detected

    def test_no_stencils_in_basic_xml(self, valid_xml_basic: str) -> None:
        root = validate_xml_wellformed(valid_xml_basic)
        detected = detect_stencils(root)
        assert len(detected) == 0


class TestStencilValidation:
    """Tests for stencil policy validation."""

    def test_allowed_stencil_passes(self, valid_xml_with_aws: str) -> None:
        root = validate_xml_wellformed(valid_xml_with_aws)
        detected = detect_stencils(root)
        violations = validate_stencils(detected, ["aws4", "gcp2"])
        assert len(violations) == 0

    def test_disallowed_stencil_fails(self, valid_xml_with_aws: str) -> None:
        root = validate_xml_wellformed(valid_xml_with_aws)
        detected = detect_stencils(root)
        violations = validate_stencils(detected, ["gcp2", "azure"])
        assert len(violations) >= 1
        assert any(v.stencil_id == "aws4" for v in violations)


class TestArchiMateLicenseCheck:
    """Tests for ArchiMate license requirement detection."""

    def test_archimate_detected(self, valid_xml_with_archimate: str) -> None:
        root = validate_xml_wellformed(valid_xml_with_archimate)
        detected = detect_stencils(root)
        assert requires_archimate_license(detected) is True

    def test_archimate_not_detected(self, valid_xml_basic: str) -> None:
        root = validate_xml_wellformed(valid_xml_basic)
        detected = detect_stencils(root)
        assert requires_archimate_license(detected) is False


class TestXMLLinterFullValidation:
    """Tests for the full validation orchestrator."""

    def test_compliant_diagram(self, valid_xml_basic: str) -> None:
        settings = Settings(
            ALLOWED_COLORS="4A90D9,333333,1A1A1A",
            ALLOWED_STENCILS="aws4,gcp2,azure,archimate3,c4,cisco,oci",
        )
        linter = XMLLinter(settings)
        result = linter.full_validation(valid_xml_basic)
        assert result.level == ComplianceLevel.COMPLIANT
        assert result.xml_well_formed is True
        assert len(result.errors) == 0

    def test_color_violation_blocks(self, valid_xml_with_disallowed_color: str) -> None:
        settings = Settings(
            ALLOWED_COLORS="333333",
            ALLOWED_STENCILS="",
        )
        linter = XMLLinter(settings)
        result = linter.full_validation(valid_xml_with_disallowed_color)
        assert result.level == ComplianceLevel.BLOCKED
        assert len(result.color_violations) >= 1

    def test_stencil_violation_blocks(self, valid_xml_with_aws: str) -> None:
        settings = Settings(
            ALLOWED_STENCILS="gcp2,azure",
            ALLOWED_COLORS="",
        )
        linter = XMLLinter(settings)
        result = linter.full_validation(valid_xml_with_aws)
        assert result.level == ComplianceLevel.BLOCKED
        assert len(result.stencil_violations) >= 1

    def test_archimate_no_license_blocks(self, valid_xml_with_archimate: str) -> None:
        settings = Settings(
            ALLOWED_STENCILS="aws4,gcp2,azure,archimate3,c4,cisco,oci",
            ARCHIMATE_LICENSE_KEY="",
            ALLOWED_COLORS="",
        )
        linter = XMLLinter(settings)
        result = linter.full_validation(valid_xml_with_archimate)
        assert result.level == ComplianceLevel.BLOCKED
        assert result.requires_archimate_license is True
        assert result.archimate_license_valid is False

    def test_archimate_with_license_passes(self, valid_xml_with_archimate: str) -> None:
        settings = Settings(
            ALLOWED_STENCILS="aws4,gcp2,azure,archimate3,c4,cisco,oci",
            ARCHIMATE_LICENSE_KEY="valid-key-123",
            ALLOWED_COLORS="4A90D9,333333",
        )
        linter = XMLLinter(settings)
        result = linter.full_validation(valid_xml_with_archimate)
        assert result.archimate_license_valid is True

    def test_malformed_xml_blocks(self, invalid_xml: str) -> None:
        linter = XMLLinter(Settings())
        result = linter.full_validation(invalid_xml)
        assert result.level == ComplianceLevel.BLOCKED
        assert result.xml_well_formed is False