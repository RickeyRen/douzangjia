from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from constructor values or environment."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    archive_root: Path = Field(validation_alias=AliasChoices("ARCHIVE_ROOT", "archive_root"))
    master_key: SecretStr = Field(
        validation_alias=AliasChoices("ARCHIVE_MASTER_KEY", "MASTER_KEY", "master_key")
    )
    web_dist: Path | None = Field(
        default=None, validation_alias=AliasChoices("WEB_DIST", "web_dist")
    )
    bind_host: str = Field(
        default="0.0.0.0",
        validation_alias=AliasChoices("APP_BIND_HOST", "BIND_HOST", "bind_host"),
    )
    port: int = Field(
        default=8099,
        ge=1,
        le=65535,
        validation_alias=AliasChoices("APP_PORT", "PORT", "port"),
    )
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

    @field_validator("web_dist")
    @classmethod
    def resolve_web_dist(cls, value: Path | None) -> Path | None:
        return value.expanduser().resolve() if value is not None else None
