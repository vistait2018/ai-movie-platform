from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )
    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    database_url: SecretStr | None = None
    redis_url: SecretStr | None = None
    readiness_timeout_seconds: float = Field(default=2, ge=0.1, le=10)

    registration_requests_per_window: int = Field(default=10, ge=1, le=1000)
    registration_window_seconds: int = Field(default=60, ge=1, le=3600)
    access_signing_key: SecretStr | None = None
    access_token_seconds: int = Field(default=600, ge=60, le=3600)
    access_token_issuer: str = Field(default="ai-movie-platform", min_length=1, max_length=200)
    access_token_audience: str = Field(default="ai-movie-clients", min_length=1, max_length=200)
    login_requests_per_window: int = Field(default=10, ge=1, le=1000)
    login_window_seconds: int = Field(default=60, ge=1, le=3600)
    refresh_token_seconds: int = Field(default=604800, ge=600, le=7776000)
    refresh_session_seconds: int = Field(default=2592000, ge=3600, le=7776000)
    session_requests_per_window: int = Field(default=30, ge=1, le=1000)
    session_window_seconds: int = Field(default=60, ge=1, le=3600)
    email_outbox_key: SecretStr | None = None
    verification_seconds: int = Field(default=3600, ge=60, le=86400)
    password_reset_seconds: int = Field(default=900, ge=60, le=3600)
    action_resend_seconds: int = Field(default=60, ge=1, le=3600)
    action_requests_per_window: int = Field(default=5, ge=1, le=100)
    action_confirmations_per_window: int = Field(default=20, ge=1, le=100)
    action_window_seconds: int = Field(default=300, ge=1, le=3600)
    email_provider: Literal["outbox", "mailtrap_sandbox", "smtp"] = "outbox"
    smtp_host: str | None = None
    smtp_port: int = Field(default=2525, ge=1, le=65535)
    smtp_username: SecretStr | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = True
    smtp_timeout_seconds: float = Field(default=10, ge=1, le=30)
    email_from_address: EmailStr | None = None
    email_from_name: str = Field(default="AI Movie Platform", max_length=100)

    @field_validator(
        "smtp_host", "smtp_username", "smtp_password", "email_from_address", mode="before"
    )
    @classmethod
    def empty_email_setting(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_services(self) -> "Settings":
        if self.refresh_token_seconds <= self.access_token_seconds:
            raise ValueError("Refresh lifetime must exceed access lifetime")
        if self.refresh_session_seconds < self.refresh_token_seconds:
            raise ValueError("Session lifetime must cover refresh lifetime")
        for name, secret, schemes in (
            ("database_url", self.database_url, {"postgresql", "postgres"}),
            ("redis_url", self.redis_url, {"redis", "rediss"}),
        ):
            if secret is None:
                if self.environment in {"staging", "production"}:
                    raise ValueError(f"{name} is required outside local development/testing")
                continue
            parsed = urlsplit(secret.get_secret_value())
            if parsed.scheme not in schemes or not parsed.hostname:
                raise ValueError(f"{name} must be a supported service URL")
            if self.environment in {"staging", "production"}:
                if not parsed.password or parsed.password.startswith("replace-"):
                    raise ValueError(f"{name} requires a non-placeholder password")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
