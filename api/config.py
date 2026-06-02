"""
Configuración de la API del normalizador C4 (Pydantic settings).

Se carga desde variables de entorno / archivo .env. Todo es opcional: con los
valores por defecto el servicio arranca sin dependencias externas.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Ajustes de la aplicación, leídos de variables de entorno."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Seguridad
    api_key: str = ""
    cors_origins: str = "*"

    # Rate limiting (ventana fija por IP)
    rate_limit_enabled: bool = True
    rate_limit_normalize_per_minute: int = 60

    # Límite de tamaño del payload XML
    max_xml_payload_size: int = 10_485_760  # 10 MB

    # Logging
    log_level: str = "info"

    # Compliance opcional (usado por api/linting.py)
    allowed_stencils: str = Field(
        default="aws4,gcp2,azure,archimate3,c4,cisco,oci",
        validation_alias=AliasChoices("allowed_stencils", "ALLOWED_STENCILS"),
    )
    allowed_colors: str = Field(
        default="",
        validation_alias=AliasChoices("allowed_colors", "ALLOWED_COLORS"),
    )
    archimate_license_key: str = Field(
        default="",
        validation_alias=AliasChoices("archimate_license_key", "ARCHIMATE_LICENSE_KEY"),
    )

    # ---- Propiedades derivadas ---------------------------------------------

    @property
    def allowed_stencils_list(self) -> list[str]:
        if not self.allowed_stencils.strip():
            return []
        return [s.strip().lower() for s in self.allowed_stencils.split(",") if s.strip()]

    @property
    def allowed_colors_list(self) -> list[str]:
        if not self.allowed_colors.strip():
            return []
        return [c.strip().upper().lstrip("#") for c in self.allowed_colors.split(",") if c.strip()]

    @property
    def has_archimate_license(self) -> bool:
        return bool(self.archimate_license_key and self.archimate_license_key.strip())

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_color_validation_enabled(self) -> bool:
        return len(self.allowed_colors_list) > 0


@lru_cache
def get_settings() -> Settings:
    """Instancia cacheada de Settings (singleton)."""
    return Settings()
