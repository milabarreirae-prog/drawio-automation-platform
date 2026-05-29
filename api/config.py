"""
Application configuration using Pydantic BaseSettings.

All configuration is loaded from environment variables with sensible defaults.
Uses python-dotenv for .env file support.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # =========================================================================
    # Redis Configuration
    # =========================================================================
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_max_connections: int = 20

    # =========================================================================
    # ARQ Configuration
    # =========================================================================
    arq_health_check_interval: int = 1
    arq_max_jobs: int = 20
    arq_job_timeout: int = 300
    arq_expires: int = 3600

    # =========================================================================
    # S3 / MinIO Storage Configuration
    # =========================================================================
    s3_endpoint_url: Optional[str] = None
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket_name: str = "drawio-exports"
    s3_region: str = "us-east-1"
    s3_key_prefix: str = ""
    s3_presigned_url_expires: int = 3600

    # =========================================================================
    # Export Configuration
    # =========================================================================
    default_export_format: str = "svg"
    allowed_export_formats: str = "svg,png,pdf"
    default_export_scale: float = 1.0

    # =========================================================================
    # Stencils Configuration
    # =========================================================================
    allowed_stencils: str = Field(
        default="aws4,gcp2,azure,archimate3,c4,cisco,oci",
        validation_alias=AliasChoices("allowed_stencils", "ALLOWED_STENCILS"),
    )

    # =========================================================================
    # Corporate Compliance: Allowed Colors
    # =========================================================================
    allowed_colors: str = Field(
        default="",
        validation_alias=AliasChoices("allowed_colors", "ALLOWED_COLORS"),
    )

    # =========================================================================
    # ArchiMate License
    # =========================================================================
    archimate_license_key: str = Field(
        default="",
        validation_alias=AliasChoices("archimate_license_key", "ARCHIMATE_LICENSE_KEY"),
    )

    # =========================================================================
    # Worker Configuration
    # =========================================================================
    worker_max_jobs: int = 3
    worker_job_timeout: int = 300
    worker_render_max_retries: int = 2
    worker_render_retry_backoff: int = 2

    # =========================================================================
    # Chromium / Draw.io
    # =========================================================================
    chromium_flags: str = "--no-sandbox --disable-gpu --disable-dev-shm-usage --disable-setuid-sandbox --single-process"
    drawio_cli_path: str = "/opt/drawio/drawio"

    # =========================================================================
    # Webhook Configuration
    # =========================================================================
    webhook_default_url: str = ""
    webhook_timeout: int = 30
    webhook_max_retries: int = 2

    # =========================================================================
    # Logging Configuration
    # =========================================================================
    log_level: str = "info"
    log_format: str = "json"
    access_log_enabled: bool = True

    # =========================================================================
    # Security Configuration
    # =========================================================================
    api_key: str = ""
    cors_origins: str = "*"

    # =========================================================================
    # Resource Limits
    # =========================================================================
    max_xml_payload_size: int = 10_485_760  # 10 MB

    # =========================================================================
    # Computed Properties
    # =========================================================================

    @property
    def allowed_stencils_list(self) -> list[str]:
        """Parse ALLOWED_STENCILS into a list of stencil IDs."""
        if not self.allowed_stencils.strip():
            return []
        return [s.strip().lower() for s in self.allowed_stencils.split(",") if s.strip()]

    @property
    def allowed_colors_list(self) -> list[str]:
        """Parse ALLOWED_COLORS into a list of uppercase hex colors without #."""
        if not self.allowed_colors.strip():
            return []
        return [c.strip().upper().lstrip("#") for c in self.allowed_colors.split(",") if c.strip()]

    @property
    def has_archimate_license(self) -> bool:
        """Check if a valid ArchiMate license key is configured."""
        return bool(self.archimate_license_key and self.archimate_license_key.strip())

    @property
    def allowed_export_formats_list(self) -> list[str]:
        """Parse ALLOWED_EXPORT_FORMATS into a list."""
        return [f.strip().lower() for f in self.allowed_export_formats.split(",") if f.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS into a list, or ['*'] for wildcard."""
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def redis_url(self) -> str:
        """Build Redis connection URL from individual settings."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def is_color_validation_enabled(self) -> bool:
        """Check if color validation is enabled (non-empty ALLOWED_COLORS)."""
        return len(self.allowed_colors_list) > 0


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance (singleton pattern)."""
    return Settings()