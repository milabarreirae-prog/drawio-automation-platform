#!/usr/bin/env python3
"""
Stencil Fetcher Script

Downloads stencil libraries from their source URLs defined in stencils/manifest.json.
Supports:
- Retry with exponential backoff for transient failures
- SHA256 integrity verification
- Offline mode (skip download, use cached stencils)
- Structured JSON logging
- Concurrent downloads for speed

Usage:
    python scripts/fetch_stencils.py              # Download all stencils
    python scripts/fetch_stencils.py --offline     # Validate cache only, no downloads
    python scripts/fetch_stencils.py --stencil aws4,gcp2  # Download specific stencils
    python scripts/fetch_stencils.py --force       # Force re-download even if cached
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

# ============================================================================
# Configuration
# ============================================================================

MANIFEST_PATH = Path("stencils/manifest.json")
DOWNLOAD_DIR = Path("stencils/downloaded")
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds
REQUEST_TIMEOUT = 120  # seconds for large stencil XML files
CONCURRENT_DOWNLOADS = 4
CHUNK_SIZE = 8192  # bytes for streaming download

# ============================================================================
# Structured Logging
# ============================================================================


def setup_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            '{"timestamp":"%(asctime)s","level":"%(levelname)s","message":"%(message)s"}',
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class StencilInfo:
    """Parsed stencil metadata from manifest."""

    stencil_id: str
    name: str
    type: str
    source_url: Optional[str]
    sha256: Optional[str]
    lib_param: Optional[str]

    @classmethod
    def from_manifest_entry(cls, stencil_id: str, data: dict) -> "StencilInfo":
        return cls(
            stencil_id=stencil_id,
            name=data.get("name", stencil_id),
            type=data.get("type", "unknown"),
            source_url=data.get("source_url"),
            sha256=data.get("sha256"),
            lib_param=data.get("lib_param"),
        )


@dataclass
class FetchResult:
    """Result of a single stencil fetch operation."""

    stencil_id: str
    success: bool
    file_path: Optional[Path] = None
    sha256_computed: Optional[str] = None
    error: Optional[str] = None
    retries: int = 0
    from_cache: bool = False

    def to_dict(self) -> dict:
        return {
            "stencil_id": self.stencil_id,
            "success": self.success,
            "file_path": str(self.file_path) if self.file_path else None,
            "sha256": self.sha256_computed,
            "error": self.error,
            "retries": self.retries,
            "from_cache": self.from_cache,
        }


@dataclass
class SummaryReport:
    """Aggregated summary of all fetch operations."""

    total: int = 0
    successful: int = 0
    failed: int = 0
    skipped_unavailable: int = 0
    from_cache: int = 0
    results: list[FetchResult] = field(default_factory=list)

    def add(self, result: FetchResult) -> None:
        self.total += 1
        self.results.append(result)
        if result.success:
            self.successful += 1
            if result.from_cache:
                self.from_cache += 1
        else:
            self.failed += 1

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "successful": self.successful,
            "failed": self.failed,
            "skipped_unavailable": self.skipped_unavailable,
            "from_cache": self.from_cache,
            "results": [r.to_dict() for r in self.results],
        }


# ============================================================================
# Manifest Loading
# ============================================================================


def load_manifest(manifest_path: Path = MANIFEST_PATH) -> dict:
    """Load and validate the stencil manifest."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    if "stencils" not in manifest:
        raise ValueError("Manifest missing required 'stencils' key")

    logger.info("Loaded manifest v%s with %d stencils", manifest.get("version", "unknown"), len(manifest["stencils"]))
    return manifest


# ============================================================================
# SHA256 Verification
# ============================================================================


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            sha.update(chunk)
    return sha.hexdigest()


def verify_integrity(file_path: Path, expected_sha256: Optional[str]) -> bool:
    """Verify file integrity against expected SHA256 hash. If no hash provided, skip verification."""
    if expected_sha256 is None:
        logger.debug("No SHA256 in manifest for %s, skipping integrity check", file_path.name)
        return True

    computed = compute_sha256(file_path)
    if computed != expected_sha256:
        logger.warning("SHA256 mismatch for %s: expected %s, got %s", file_path.name, expected_sha256, computed)
        return False

    logger.debug("SHA256 verified for %s: %s", file_path.name, computed[:16])
    return True


# ============================================================================
# Stencil Downloader
# ============================================================================


class StencilDownloader:
    """Async downloader with retry, streaming, and integrity verification."""

    def __init__(self, force: bool = False, offline: bool = False):
        self.force = force
        self.offline = offline
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(REQUEST_TIMEOUT),
                limits=httpx.Limits(max_connections=CONCURRENT_DOWNLOADS),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _output_path(self, stencil_id: str) -> Path:
        """Determine output file path for a stencil."""
        return DOWNLOAD_DIR / f"{stencil_id}.xml"

    def _metadata_path(self, stencil_id: str) -> Path:
        """Determine metadata file path for a stencil."""
        return DOWNLOAD_DIR / f"{stencil_id}.metadata.json"

    def _is_cached(self, stencil: StencilInfo) -> Optional[Path]:
        """Check if stencil is already cached and valid."""
        xml_path = self._output_path(stencil.stencil_id)
        meta_path = self._metadata_path(stencil.stencil_id)

        if not xml_path.exists():
            return None

        # Check integrity if SHA256 is provided
        if stencil.sha256 and not verify_integrity(xml_path, stencil.sha256):
            logger.info("Cached stencil %s failed integrity check, will re-download", stencil.stencil_id)
            return None

        # Check metadata freshness
        if meta_path.exists():
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
                age_hours = (datetime.now(timezone.utc) - datetime.fromisoformat(meta["downloaded_at"])).total_seconds() / 3600
                logger.debug("Cached stencil %s age: %.1f hours", stencil.stencil_id, age_hours)
            except (json.JSONDecodeError, KeyError, ValueError):
                pass

        return xml_path

    async def fetch_one(self, stencil: StencilInfo) -> FetchResult:
        """Download a single stencil with retry logic."""
        if stencil.type == "unavailable":
            logger.info("Stencil %s marked as unavailable, skipping", stencil.stencil_id)
            return FetchResult(
                stencil_id=stencil.stencil_id,
                success=False,
                error="Stencil marked as unavailable in manifest",
            )

        if stencil.source_url is None:
            logger.warning("Stencil %s has no source_url, skipping", stencil.stencil_id)
            return FetchResult(
                stencil_id=stencil.stencil_id,
                success=False,
                error="No source URL defined in manifest",
            )

        # Check cache (unless forced)
        if not self.force:
            cached = self._is_cached(stencil)
            if cached is not None:
                logger.info("Using cached stencil: %s (%s)", stencil.stencil_id, cached)
                sha = compute_sha256(cached) if not stencil.sha256 else stencil.sha256
                return FetchResult(
                    stencil_id=stencil.stencil_id,
                    success=True,
                    file_path=cached,
                    sha256_computed=sha,
                    from_cache=True,
                )

        if self.offline:
            logger.warning("Offline mode: stencil %s not cached, skipping download", stencil.stencil_id)
            return FetchResult(
                stencil_id=stencil.stencil_id,
                success=False,
                error="Not cached and offline mode is enabled",
            )

        # Download with retry
        client = await self._get_client()
        last_error: Optional[str] = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                logger.info("Downloading %s from %s (attempt %d/%d)", stencil.stencil_id, stencil.source_url, attempt + 1, MAX_RETRIES + 1)

                response = await client.get(stencil.source_url)
                response.raise_for_status()

                # Ensure download directory exists
                DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

                # Write stencil XML
                xml_path = self._output_path(stencil.stencil_id)
                content = response.content
                with open(xml_path, "wb") as f:
                    f.write(content)

                # Compute hash
                sha = compute_sha256(xml_path)

                # Verify integrity if expected hash is provided
                if stencil.sha256 and sha != stencil.sha256:
                    logger.error("SHA256 mismatch for %s: expected %s, got %s", stencil.stencil_id, stencil.sha256, sha)
                    xml_path.unlink(missing_ok=True)
                    return FetchResult(
                        stencil_id=stencil.stencil_id,
                        success=False,
                        error=f"SHA256 mismatch: expected {stencil.sha256}, got {sha}",
                        retries=attempt,
                    )

                # Write metadata
                meta = {
                    "stencil_id": stencil.stencil_id,
                    "name": stencil.name,
                    "source_url": stencil.source_url,
                    "sha256": sha,
                    "file_size_bytes": len(content),
                    "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "version": getattr(stencil, "version", None),
                }
                with open(self._metadata_path(stencil.stencil_id), "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)

                logger.info("Successfully downloaded %s (%.1f KB, SHA256: %s)", stencil.stencil_id, len(content) / 1024, sha[:16])
                return FetchResult(
                    stencil_id=stencil.stencil_id,
                    success=True,
                    file_path=xml_path,
                    sha256_computed=sha,
                    retries=attempt,
                )

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                last_error = f"HTTP {status}: {e.response.reason_phrase}"

                # Don't retry client errors (4xx) except 429 (rate limit)
                if 400 <= status < 500 and status != 429:
                    logger.error("Non-retryable HTTP error for %s: %s", stencil.stencil_id, last_error)
                    break

            except httpx.TimeoutException:
                last_error = f"Timeout after {REQUEST_TIMEOUT}s"

            except httpx.RequestError as e:
                last_error = f"Request error: {e}"

            except OSError as e:
                last_error = f"OS error: {e}"

            if attempt < MAX_RETRIES:
                backoff = RETRY_BACKOFF_BASE ** (attempt + 1)
                logger.warning("Retry %d/%d for %s after %s (backoff: %ds)", attempt + 1, MAX_RETRIES, stencil.stencil_id, last_error, backoff)
                await asyncio.sleep(backoff)

        logger.error("Failed to download %s after %d retries: %s", stencil.stencil_id, MAX_RETRIES, last_error)
        return FetchResult(
            stencil_id=stencil.stencil_id,
            success=False,
            error=last_error or "Unknown error",
            retries=MAX_RETRIES,
        )

    async def fetch_all(self, stencils: dict[str, dict], filter_ids: Optional[list[str]] = None) -> SummaryReport:
        """Download all stencils concurrently with rate limiting."""
        report = SummaryReport()
        semaphore = asyncio.Semaphore(CONCURRENT_DOWNLOADS)

        async def fetch_with_limit(stencil_id: str, data: dict) -> None:
            if filter_ids and stencil_id not in filter_ids:
                return

            stencil = StencilInfo.from_manifest_entry(stencil_id, data)

            if stencil.type == "unavailable":
                report.skipped_unavailable += 1
                logger.info("Skipping unavailable stencil: %s", stencil_id)
                return

            async with semaphore:
                result = await self.fetch_one(stencil)
                report.add(result)

        tasks = [fetch_with_limit(sid, sdata) for sid, sdata in stencils.items()]
        await asyncio.gather(*tasks)

        return report


# ============================================================================
# Report Generation
# ============================================================================


def print_summary(report: SummaryReport) -> None:
    """Print a human-readable summary of fetch results."""
    print("\n" + "=" * 60)
    print("  STENCIL FETCH SUMMARY")
    print("=" * 60)
    print(f"  Total stencils processed:  {report.total}")
    print(f"  Successfully downloaded:   {report.successful}")
    print(f"  From cache:                {report.from_cache}")
    print(f"  Failed:                    {report.failed}")
    print(f"  Skipped (unavailable):     {report.skipped_unavailable}")
    print("-" * 60)

    if report.failed > 0:
        print("\n  FAILED STENCILS:")
        for r in report.results:
            if not r.success and r.stencil_id not in ["leanix"]:
                print(f"    ✗ {r.stencil_id}: {r.error}")
    print("=" * 60)

    if report.failed > 0:
        sys.exit(1)


# ============================================================================
# CLI Entry Point
# ============================================================================


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download stencil libraries for drawio-automation-platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                     Download all available stencils
  %(prog)s --offline            Validate cached stencils without downloading
  %(prog)s --stencil aws4,gcp2  Download specific stencils only
  %(prog)s --force              Force re-download all stencils
  %(prog)s --log-level debug    Enable debug logging
        """,
    )

    parser.add_argument("--offline", action="store_true", help="Skip downloads, only validate cached stencils")
    parser.add_argument("--force", action="store_true", help="Force re-download even if stencils are cached")
    parser.add_argument("--stencil", type=str, help="Comma-separated list of stencil IDs to download (default: all)")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Logging level")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH, help=f"Path to manifest file (default: {MANIFEST_PATH})")

    return parser.parse_args()


async def main() -> None:
    """Main entry point for the stencil fetcher."""
    args = parse_args()

    setup_logging(args.log_level)

    # Load manifest
    try:
        manifest = load_manifest(args.manifest)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        logger.error("Failed to load manifest: %s", e)
        sys.exit(1)

    stencils_data = manifest.get("stencils", {})
    if not stencils_data:
        logger.error("No stencils defined in manifest")
        sys.exit(1)

    # Parse stencil filter
    filter_ids = None
    if args.stencil:
        filter_ids = [s.strip() for s in args.stencil.split(",")]
        # Validate stencil IDs
        unknown = set(filter_ids) - set(stencils_data.keys())
        if unknown:
            logger.error("Unknown stencil IDs: %s", ", ".join(unknown))
            logger.info("Available stencils: %s", ", ".join(sorted(stencils_data.keys())))
            sys.exit(1)

    # Ensure download directory exists
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Download stencils
    start_time = time.monotonic()
    downloader = StencilDownloader(force=args.force, offline=args.offline)

    try:
        report = await downloader.fetch_all(stencils_data, filter_ids)
        elapsed = time.monotonic() - start_time

        logger.info("Fetch completed in %.1f seconds", elapsed)
        print_summary(report)

        # Write summary report
        report_path = DOWNLOAD_DIR / "fetch_report.json"
        report_data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(elapsed, 2),
            **report.to_dict(),
        }
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
        logger.info("Report written to %s", report_path)

    finally:
        await downloader.close()


if __name__ == "__main__":
    asyncio.run(main())