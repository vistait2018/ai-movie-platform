import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from pydantic import SecretStr, ValidationError

from app.core.settings import Settings, get_settings
from app.main import app


def pytest_addoption(parser):
    parser.addoption(
        "--service-env-file",
        type=Path,
        default=None,
        help="Service settings file (default: repository .env; environment overrides file)",
    )


def _windows_host_url(secret):
    if sys.platform != "win32":
        return secret
    parts = urlsplit(secret.get_secret_value())
    if parts.hostname != "localhost":
        return secret
    userinfo = parts.netloc.rsplit("@", 1)[0] + "@" if "@" in parts.netloc else ""
    port = f":{parts.port}" if parts.port is not None else ""
    return SecretStr(urlunsplit(parts._replace(netloc=f"{userinfo}127.0.0.1{port}")))


@pytest.fixture(scope="session")
def service_settings(pytestconfig):
    # Session scope captures explicit service settings before function isolation clears APP_*.
    explicit = pytestconfig.getoption("--service-env-file")
    env_file = explicit if explicit is not None else pytestconfig.rootpath / ".env"
    if explicit is not None and not env_file.is_file():
        raise pytest.UsageError("The specified service settings file does not exist")
    try:
        config = Settings(_env_file=env_file, environment="test")
    except (ValidationError, ValueError):
        raise pytest.UsageError(
            "Invalid integration settings; check service URLs and timeout"
        ) from None
    if config.database_url is None or config.redis_url is None:
        raise pytest.UsageError(
            "Integration requires APP_DATABASE_URL and APP_REDIS_URL in the process environment "
            "or local .env; use --service-env-file to select another file"
        )
    return config.model_copy(
        update={
            "database_url": _windows_host_url(config.database_url),
            "redis_url": _windows_host_url(config.redis_url),
        }
    )


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    # Unit tests never inherit an operator's local service credentials or environment.
    for key in ("APP_DATABASE_URL", "APP_REDIS_URL", "APP_READINESS_TIMEOUT_SECONDS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    get_settings.cache_clear()
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    get_settings.cache_clear()
