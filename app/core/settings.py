from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
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
    email_outbox_key: SecretStr | None = None
    verification_seconds: int = Field(default=3600, ge=60, le=86400)
    password_reset_seconds: int = Field(default=900, ge=60, le=3600)
    action_resend_seconds: int = Field(default=60, ge=1, le=3600)
    action_requests_per_window: int = Field(default=5, ge=1, le=100)
    action_confirmations_per_window: int = Field(default=20, ge=1, le=100)
    action_window_seconds: int = Field(default=300, ge=1, le=3600)

    @model_validator(mode="after")
    def validate_services(self) -> "Settings":
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
