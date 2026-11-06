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
    from cryptography.fernet import Fernet

    # Unit tests never inherit an operator's local service credentials or environment.
    for key in (
        "APP_BROWSER_ORIGINS",
        "APP_MFA_ENCRYPTION_KEY",
        "APP_MFA_ENROLLMENT_SECONDS",
        "APP_MFA_ASSURANCE_SECONDS",
        "APP_MFA_REQUESTS_PER_WINDOW",
        "APP_MFA_WINDOW_SECONDS",
        "APP_TRUSTED_HOSTS",
        "APP_BROWSER_COOKIE_SECURE",
        "APP_BROWSER_COOKIE_SECONDS",
        "APP_BROWSER_CSRF_SECONDS",
        "APP_DATABASE_URL",
        "APP_REDIS_URL",
        "APP_READINESS_TIMEOUT_SECONDS",
        "APP_ACCESS_SIGNING_KEY",
        "APP_ACCESS_TOKEN_SECONDS",
        "APP_ACCESS_TOKEN_ISSUER",
        "APP_ACCESS_TOKEN_AUDIENCE",
        "APP_REFRESH_TOKEN_SECONDS",
        "APP_REFRESH_SESSION_SECONDS",
        "APP_SESSION_REQUESTS_PER_WINDOW",
        "APP_SESSION_WINDOW_SECONDS",
        "APP_LOGIN_REQUESTS_PER_WINDOW",
        "APP_LOGIN_WINDOW_SECONDS",
        "APP_VERIFICATION_SECONDS",
        "APP_PASSWORD_RESET_SECONDS",
        "APP_ACTION_RESEND_SECONDS",
        "APP_ACTION_REQUESTS_PER_WINDOW",
        "APP_ACTION_CONFIRMATIONS_PER_WINDOW",
        "APP_ACTION_WINDOW_SECONDS",
        "APP_SMTP_HOST",
        "APP_SMTP_PORT",
        "APP_SMTP_USERNAME",
        "APP_SMTP_PASSWORD",
        "APP_SMTP_STARTTLS",
        "APP_SMTP_TIMEOUT_SECONDS",
        "APP_EMAIL_FROM_ADDRESS",
        "APP_EMAIL_FROM_NAME",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    monkeypatch.setenv("APP_EMAIL_PROVIDER", "outbox")
    monkeypatch.setenv("APP_EMAIL_OUTBOX_KEY", Fernet.generate_key().decode())

    def forbid_live_smtp(*args, **kwargs):
        raise AssertionError("Live SMTP is forbidden in automated tests; use an explicit mock")

    monkeypatch.setattr("smtplib.SMTP", forbid_live_smtp)
    get_settings.cache_clear()
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def disposable_identity_database(request):
    import os

    if os.getenv("RUN_SERVICE_TESTS") != "1":
        pytest.skip("Requires isolated real PostgreSQL")
    service_settings = request.getfixturevalue("service_settings")
    import re
    from contextlib import contextmanager
    from uuid import uuid4

    import psycopg
    from psycopg import sql
    from sqlalchemy.engine import make_url

    from app.db.session import build_engine

    @contextmanager
    def database():
        name = "movie_auth_test_" + uuid4().hex
        if not re.fullmatch(r"movie_auth_test_[0-9a-f]{32}", name):
            raise RuntimeError("Unexpected disposable database name")
        admin_url = service_settings.database_url.get_secret_value()
        if make_url(admin_url).host not in {"127.0.0.1", "localhost", "::1", "postgres"}:
            raise RuntimeError("Disposable database tests require explicitly local services")
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        engine = build_engine(
            make_url(admin_url).set(database=name).render_as_string(hide_password=False)
        )
        try:
            yield engine
        finally:
            engine.dispose()
            # Only this newly created, checked test database is ever dropped. No existing DB/volume.
            if not re.fullmatch(r"movie_auth_test_[0-9a-f]{32}", name):
                raise RuntimeError("Refusing cleanup of an unexpected database name")
            with psycopg.connect(admin_url, autocommit=True) as admin:
                admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))

    return database


@pytest.fixture(scope="session")
def identity_engine(disposable_identity_database):
    from alembic import command
    from alembic.config import Config

    with disposable_identity_database() as engine:
        config = Config("alembic.ini")
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine


@pytest.fixture
def migration_engine(disposable_identity_database):
    with disposable_identity_database() as engine:
        yield engine
