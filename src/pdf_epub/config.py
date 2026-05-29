from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "pdf-epub"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    upload_dir: Path = Path("/tmp/pdf_epub/uploads")
    epub_dir: Path = Path("/tmp/pdf_epub/epubs")
    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MB

    ocr_lang: str = "spa+eng"

    # Set to restrict CORS in production, e.g. '["https://yourapp.com"]'
    cors_origins: list[str] = Field(default=["*"])

    # Authentication — leave unset to disable (development / local use)
    api_key: str | None = Field(default=None)

    # Expose /metrics endpoint (Prometheus). Restrict at the reverse-proxy in production.
    metrics_enabled: bool = True

    # Conversion safety limits
    max_pages: int = Field(default=1000, ge=1)
    max_conversion_seconds: int = Field(default=300, ge=30)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
