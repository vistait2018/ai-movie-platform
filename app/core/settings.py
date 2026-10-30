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
