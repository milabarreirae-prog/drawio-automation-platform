"""
S3/MinIO Uploader for Render Output.

Provides an async wrapper around boto3 for uploading rendered
diagrams to S3 or MinIO. Supports:
- Custom endpoint URL (for MinIO)
- Presigned URL generation for time-limited access
- Content-type detection per export format
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from api.config import Settings, get_settings

logger = logging.getLogger(__name__)


class S3Uploader:
    """
    Async-compatible S3/MinIO upload handler.

    Uses boto3 with configurable endpoint, credentials, and bucket.

    Usage:
        uploader = S3Uploader()
        url, key = await uploader.upload("/path/to/file.svg", "task-123", "svg")
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

        boto_config = BotoConfig(
            region_name=self.settings.s3_region,
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
        )

        self._client = boto3.client(
            "s3",
            endpoint_url=self.settings.s3_endpoint_url or None,
            aws_access_key_id=self.settings.s3_access_key,
            aws_secret_access_key=self.settings.s3_secret_key,
            config=boto_config,
        )

    # -------------------------------------------------------------------------
    # Content-Type Mapping
    # -------------------------------------------------------------------------

    CONTENT_TYPES: dict[str, str] = {
        "svg": "image/svg+xml",
        "png": "image/png",
        "pdf": "application/pdf",
    }

    @classmethod
    def get_content_type(cls, export_format: str) -> str:
        """Map export format to MIME content type."""
        return cls.CONTENT_TYPES.get(export_format.lower(), "application/octet-stream")

    # -------------------------------------------------------------------------
    # Upload
    # -------------------------------------------------------------------------

    async def upload(
        self,
        file_path: str,
        task_id: str,
        export_format: str = "svg",
        custom_key: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Upload a file to S3/MinIO and return a presigned URL.

        Args:
            file_path: Local path to the file to upload.
            task_id: Task identifier for naming.
            export_format: File format (svg, png, pdf).
            custom_key: Custom S3 object key (generated if not provided).

        Returns:
            Tuple of (presigned_url, s3_key).

        Raises:
            FileNotFoundError: If the file does not exist.
            RuntimeError: If the upload fails.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Build S3 key
        prefix = self.settings.s3_key_prefix.rstrip("/")
        if custom_key:
            s3_key = f"{prefix}/{custom_key}" if prefix else custom_key
        else:
            sanitized_task = task_id.replace("/", "_").replace("\\", "_")
            s3_key = f"{prefix}/{sanitized_task}.{export_format}" if prefix else f"{sanitized_task}.{export_format}"

        content_type = self.get_content_type(export_format)
        file_size = path.stat().st_size
        bucket = self.settings.s3_bucket_name

        logger.info(
            "Uploading %s (%.1f KB) to s3://%s/%s",
            path.name,
            file_size / 1024,
            bucket,
            s3_key,
        )

        try:
            # Upload file
            with open(file_path, "rb") as f:
                self._client.upload_fileobj(
                    Fileobj=f,
                    Bucket=bucket,
                    Key=s3_key,
                    ExtraArgs={
                        "ContentType": content_type,
                        "ACL": "private",
                    },
                )

            logger.info("Upload complete: s3://%s/%s", bucket, s3_key)

        except (BotoCoreError, ClientError) as e:
            logger.error("S3 upload failed: %s", e)
            raise RuntimeError(f"S3 upload failed: {e}") from e

        # Generate presigned URL
        try:
            presigned_url = self._client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": bucket,
                    "Key": s3_key,
                },
                ExpiresIn=self.settings.s3_presigned_url_expires,
            )
            logger.debug("Presigned URL generated (expires in %ds)", self.settings.s3_presigned_url_expires)

        except (BotoCoreError, ClientError) as e:
            logger.warning("Failed to generate presigned URL: %s — returning key only", e)
            presigned_url = f"s3://{bucket}/{s3_key}"

        return presigned_url, s3_key

    # -------------------------------------------------------------------------
    # Bucket Verification
    # -------------------------------------------------------------------------

    async def verify_bucket(self) -> bool:
        """
        Verify that the configured S3 bucket exists and is accessible.

        Returns:
            True if the bucket is accessible, False otherwise.
        """
        try:
            self._client.head_bucket(Bucket=self.settings.s3_bucket_name)
            logger.info("Bucket '%s' exists and is accessible", self.settings.s3_bucket_name)
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "404":
                logger.error("Bucket '%s' does not exist", self.settings.s3_bucket_name)
            else:
                logger.error("Bucket '%s' access denied: %s", self.settings.s3_bucket_name, e)
            return False
        except BotoCoreError as e:
            logger.error("S3 connection error: %s", e)
            return False