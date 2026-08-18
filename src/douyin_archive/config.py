from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from constructor values or environment."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    archive_root: Path
    master_key: SecretStr
    bind_host: str = "0.0.0.0"
    port: int = Field(default=8099, ge=1, le=65535)
    sync_interval_seconds: int = Field(default=300, ge=60)
    session_ttl_seconds: int = Field(default=30 * 24 * 60 * 60, ge=300)
    secure_cookies: bool = False

    @field_validator("archive_root")
    @classmethod
    def validate_archive_root(cls, value: Path) -> Path:
        resolved = value.expanduser().resolve()
        if resolved == Path(resolved.anchor):
            raise ValueError("archive_root cannot be the filesystem root")
        return resolved
