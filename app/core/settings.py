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
    browser_origins: list[str] = ["http://127.0.0.1:8000", "http://localhost:8000"]
    trusted_hosts: list[str] = ["127.0.0.1", "localhost", "testserver"]
    browser_cookie_secure: bool = False
    browser_cookie_seconds: int = Field(default=604800, ge=60, le=7776000)
    browser_csrf_seconds: int = Field(default=900, ge=60, le=3600)
    email_outbox_key: SecretStr | None = None
    mfa_encryption_key: SecretStr | None = None
    mfa_enrollment_seconds: int = Field(default=600, ge=60, le=900)
    mfa_assurance_seconds: int = Field(default=300, ge=30, le=600)
    mfa_requests_per_window: int = Field(default=5, ge=1, le=20)
    mfa_window_seconds: int = Field(default=300, ge=60, le=900)
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
        remote = self.environment in {"staging", "production"}
        if not self.browser_origins or not self.trusted_hosts:
            raise ValueError("Explicit browser origins and trusted hosts are required")
        for origin in self.browser_origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
                or origin != f"{parsed.scheme}://{parsed.netloc}"
                or (remote and parsed.scheme != "https")
            ):
                raise ValueError("Browser origins must be exact HTTP(S) origins")
            if remote and parsed.hostname in {"localhost", "127.0.0.1", "testserver"}:
                raise ValueError("Production browser origins must be explicit deployment origins")
        for host in self.trusted_hosts:
            if not host or any(c in host for c in "*/:@?# "):
                raise ValueError("Trusted hosts must be exact hostnames")
            if remote and host in {"localhost", "127.0.0.1", "testserver"}:
                raise ValueError("Production trusted hosts must be explicit deployment hosts")
        if remote and not self.browser_cookie_secure:
            raise ValueError("Secure browser cookies are required outside local development")
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
