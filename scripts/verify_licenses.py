#!/usr/bin/env python3
"""
License Verification Script

Scans the stencil manifest (stencils/manifest.json) and detects potential
license incompatibilities with the project's AGPL-3.0 license. Generates
a THIRD_PARTY_LICENSES.md summary file.

Usage:
    python scripts/verify_licenses.py
    python scripts/verify_licenses.py --output THIRD_PARTY_LICENSES.md
    python scripts/verify_licenses.py --check-strict   # Exit with error on any issue
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

MANIFEST_PATH = Path("stencils/manifest.json")
DEFAULT_OUTPUT = Path("THIRD_PARTY_LICENSES.md")

# Licenses compatible with AGPL-3.0
AGPL_COMPATIBLE_LICENSES = frozenset({
    "agpl-3.0",
    "gpl-3.0",
    "lgpl-3.0",
    "mit",
    "bsd-2-clause",
    "bsd-3-clause",
    "apache-2.0",
    "mpl-2.0",
    "cc-by-4.0",
    "cc0-1.0",
    "isc",
    "unlicense",
})

# Licenses that are definitely incompatible
AGPL_INCOMPATIBLE_LICENSES = frozenset({
    "proprietary",
    "commercial",
    "all-rights-reserved",
})


@dataclass
class LicenseIssue:
    """Represents a detected license issue."""

    severity: str  # "error", "warning", "info"
    stencil_id: str
    message: str
    recommendation: str = ""

    def to_markdown(self) -> str:
        icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(self.severity, "•")
        return f"| {icon} {self.stencil_id} | {self.severity.upper()} | {self.message} | {self.recommendation} |"


@dataclass
class VerificationReport:
    """Aggregated license verification results."""

    stencils_total: int = 0
    stencils_checked: int = 0
    agpl_compatible: int = 0
    agpl_incompatible_strict: int = 0
    requires_license_key: int = 0
    requires_attribution: int = 0
    unavailable: int = 0
    issues: list[LicenseIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0


def load_manifest(path: Path) -> dict:
    """Load the stencil manifest."""
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if "stencils" not in data:
        raise ValueError(f"Manifest at {path} missing 'stencils' key")

    return data


def normalize_license(license_str: str) -> str:
    """Normalize a license string for comparison."""
    return license_str.strip().lower()


def is_agpl_compatible(stencil: dict) -> tuple[bool, str]:
    """Determine if a stencil's license is AGPL-3.0 compatible."""
    # Check explicit flag
    if stencil.get("agpl_compatible") is True:
        return True, "Explicitly marked as AGPL-compatible"
    if stencil.get("agpl_compatible") is False:
        return False, "Explicitly marked as AGPL-incompatible"

    # Check license string
    license_name = normalize_license(stencil.get("license", ""))
    if not license_name:
        return False, "No license specified"

    # Direct match
    if license_name in AGPL_COMPATIBLE_LICENSES:
        return True, f"License '{license_name}' is AGPL-compatible"

    # Known incompatible
    if license_name in AGPL_INCOMPATIBLE_LICENSES or "proprietary" in license_name:
        return False, f"Proprietary license '{license_name}' — may require separate review"

    # Unknown license — flag as warning
    return False, f"Unknown license '{license_name}' — manual review required"


def verify_stencil(stencil_id: str, stencil: dict) -> list[LicenseIssue]:
    """Verify a single stencil entry and return any issues found."""
    issues: list[LicenseIssue] = []

    # Check if stencil is available
    stencil_type = stencil.get("type", "unknown")
    if stencil_type == "unavailable":
        issues.append(LicenseIssue(
            severity="info",
            stencil_id=stencil_id,
            message="Stencil marked as unavailable — not included in distribution",
            recommendation="No action required. Stencil is excluded by default.",
        ))
        return issues

    # Check license presence
    if not stencil.get("license"):
        issues.append(LicenseIssue(
            severity="error",
            stencil_id=stencil_id,
            message="No license field in manifest entry",
            recommendation="Add a 'license' field specifying the stencil's license.",
        ))
        return issues

    # Check AGPL compatibility
    compatible, reason = is_agpl_compatible(stencil)
    if not compatible:
        severity = "warning" if "unknown" in reason.lower() else "warning"
        issues.append(LicenseIssue(
            severity=severity,
            stencil_id=stencil_id,
            message=f"Potential AGPL incompatibility: {reason}",
            recommendation="Verify that the stencil license permits use with AGPL-3.0 projects. Consider adding 'agpl_compatible: true' if confirmed.",
        ))

    # Check if commercial use requires license key
    if stencil.get("commercial_use") == "requires_license":
        license_env = stencil.get("license_env_var", "UNKNOWN_KEY")
        issues.append(LicenseIssue(
            severity="warning",
            stencil_id=stencil_id,
            message=f"Commercial use requires a license key ({license_env})",
            recommendation=f"Set the {license_env} environment variable for commercial deployments. Without it, rendering will be blocked.",
        ))

    # Check attribution requirement
    if stencil.get("attribution_required"):
        issues.append(LicenseIssue(
            severity="info",
            stencil_id=stencil_id,
            message=f"Attribution required: {stencil.get('vendor', 'Unknown vendor')}",
            recommendation="Ensure generated diagrams include proper attribution to the stencil vendor.",
        ))

    # Check license_url presence
    if not stencil.get("license_url"):
        issues.append(LicenseIssue(
            severity="info",
            stencil_id=stencil_id,
            message="No license_url provided in manifest",
            recommendation="Add a 'license_url' field pointing to the official license terms.",
        ))

    return issues


def verify_all(manifest: dict) -> VerificationReport:
    """Verify all stencils in the manifest."""
    stencils = manifest.get("stencils", {})
    report = VerificationReport(stencils_total=len(stencils))

    for stencil_id, stencil_data in stencils.items():
        report.stencils_checked += 1

        # Count categories
        if stencil_data.get("type") == "unavailable":
            report.unavailable += 1

        if stencil_data.get("agpl_compatible") is True:
            report.agpl_compatible += 1
        elif stencil_data.get("agpl_compatible") is False:
            report.agpl_incompatible_strict += 1

        if stencil_data.get("requires_license_key"):
            report.requires_license_key += 1

        if stencil_data.get("attribution_required"):
            report.requires_attribution += 1

        # Verify individual stencil
        issues = verify_stencil(stencil_id, stencil_data)
        report.issues.extend(issues)

    return report


def generate_markdown(manifest: dict, report: VerificationReport, output_path: Path) -> None:
    """Generate the THIRD_PARTY_LICENSES.md file."""
    lines: list[str] = []

    # Header
    lines.append("# Third-Party Licenses")
    lines.append("")
    lines.append(f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*")
    lines.append("")
    lines.append("This document lists all third-party stencil libraries used by drawio-automation-platform")
    lines.append("and their respective license terms. It is auto-generated by `scripts/verify_licenses.py`.")
    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total stencils | {report.stencils_total} |")
    lines.append(f"| AGPL-compatible | {report.agpl_compatible} |")
    lines.append(f"| Requires license key | {report.requires_license_key} |")
    lines.append(f"| Requires attribution | {report.requires_attribution} |")
    lines.append(f"| Unavailable (excluded) | {report.unavailable} |")
    lines.append(f"| Issues found | {len(report.issues)} |")
    lines.append("")

    # Issues section (if any)
    if report.issues:
        lines.append("## License Issues Detected")
        lines.append("")
        lines.append("| Stencil | Severity | Issue | Recommendation |")
        lines.append("|---------|----------|-------|----------------|")
        for issue in sorted(report.issues, key=lambda i: {"error": 0, "warning": 1, "info": 2}.get(i.severity, 3)):
            lines.append(issue.to_markdown())
        lines.append("")

    # Per-stencil details
    lines.append("## Per-Stencil License Details")
    lines.append("")

    stencils = manifest.get("stencils", {})
    for stencil_id, stencil_data in sorted(stencils.items()):
        name = stencil_data.get("name", stencil_id)
        license_name = stencil_data.get("license", "Not specified")
        license_url = stencil_data.get("license_url", "")
        vendor = stencil_data.get("vendor", "Unknown")
        commercial_use = stencil_data.get("commercial_use", "unknown")
        agpl_compat = "✅ Yes" if stencil_data.get("agpl_compatible") else "⚠️ Unknown" if stencil_data.get("agpl_compatible") is not False else "❌ No"
        requires_key = "✅ Yes" if stencil_data.get("requires_license_key") else "No"
        attribution = "Required" if stencil_data.get("attribution_required") else "Not required"
        status = "⚠️ Unavailable" if stencil_data.get("type") == "unavailable" else "✅ Available"

        lines.append(f"### {name} (`{stencil_id}`)")
        lines.append("")
        lines.append(f"| Property | Value |")
        lines.append(f"|----------|-------|")
        lines.append(f"| Vendor | {vendor} |")
        lines.append(f"| License | {license_name} |")
        lines.append(f"| License URL | {license_url or 'N/A'} |")
        lines.append(f"| Commercial Use | {commercial_use} |")
        lines.append(f"| AGPL Compatible | {agpl_compat} |")
        lines.append(f"| Requires Key | {requires_key} |")
        lines.append(f"| Attribution | {attribution} |")
        lines.append(f"| Status | {status} |")

        notes = stencil_data.get("notes", "")
        if notes:
            lines.append(f"| Notes | {notes} |")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append("*This file is auto-generated. Do not edit manually.*")
    lines.append(f"*Source manifest: `{MANIFEST_PATH}`*")
    lines.append(f"*Generator script: `scripts/verify_licenses.py`*")
    lines.append("")

    # Write file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ THIRD_PARTY_LICENSES.md written to {output_path}")


def print_report(report: VerificationReport) -> None:
    """Print verification results to console."""
    print("\n" + "=" * 60)
    print("  LICENSE VERIFICATION REPORT")
    print("=" * 60)
    print(f"  Stencils checked:          {report.stencils_checked}/{report.stencils_total}")
    print(f"  AGPL-compatible:           {report.agpl_compatible}")
    print(f"  Requires license key:      {report.requires_license_key}")
    print(f"  Requires attribution:      {report.requires_attribution}")
    print(f"  Unavailable:               {report.unavailable}")
    print(f"  Issues:                    {len(report.issues)}")
    print(f"    Errors:                  {report.error_count}")
    print(f"    Warnings:                {report.warning_count}")
    print("-" * 60)

    if report.issues:
        print("\n  DETAILS:")
        for issue in sorted(report.issues, key=lambda i: {"error": 0, "warning": 1, "info": 2}.get(i.severity, 3)):
            icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(issue.severity, "•")
            print(f"    {icon} [{issue.severity.upper()}] {issue.stencil_id}: {issue.message}")

    print("=" * 60)

    if report.error_count > 0:
        print("\n❌ Verification found license issues that require attention!")
    elif report.warning_count > 0:
        print("\n⚠️  Verification passed with warnings. Review the issues above.")
    else:
        print("\n✅ All stencil licenses verified successfully.")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify stencil licenses and generate THIRD_PARTY_LICENSES.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                       Verify licenses and print report
  %(prog)s --output CUSTOM.md     Write report to custom file
  %(prog)s --check-strict         Exit with error code on any issue
        """,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"Output file path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--check-strict", action="store_true", help="Exit with non-zero code if any issues found")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH, help=f"Path to manifest (default: {MANIFEST_PATH})")
    parser.add_argument("--no-generate", action="store_true", help="Skip generating THIRD_PARTY_LICENSES.md")

    args = parser.parse_args()

    # Load manifest
    try:
        manifest = load_manifest(args.manifest)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"❌ Error loading manifest: {e}", file=sys.stderr)
        return 1

    # Verify all stencils
    report = verify_all(manifest)

    # Print console report
    print_report(report)

    # Generate THIRD_PARTY_LICENSES.md
    if not args.no_generate:
        try:
            generate_markdown(manifest, report, args.output)
        except OSError as e:
            print(f"❌ Error writing output file: {e}", file=sys.stderr)
            return 1

    # Exit code
    if args.check_strict and report.has_errors:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())