import asyncio
import json
import logging
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.logging import JsonFormatter
from app.core.settings import Settings, get_settings
from app.main import app
from app.services import readiness as probes


def settings(**kwargs):
    return Settings(_env_file=None, **kwargs)


def configured(**kwargs):
    return settings(
        database_url="postgresql://movie:private-password@localhost/movie",
        redis_url="redis://:private-password@localhost:6379/0",
        **kwargs,
    )


def client_for(config):
    app.dependency_overrides[get_settings] = lambda: config
    return TestClient(app)


def test_liveness_does_not_require_services():
    with client_for(settings()) as client:
        response = client.get("/live")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}
        UUID(response.headers["X-Request-ID"])
        failed = client.get("/ready")
        assert failed.status_code == 503
        assert failed.json() == {
            "status": "not_ready",
            "checks": {"database": "unconfigured", "redis": "unconfigured"},
        }


def test_readiness_success_checks_both_dependencies(monkeypatch):
    database = AsyncMock()
    redis = AsyncMock()
    monkeypatch.setattr(probes, "ping_database", database)
    monkeypatch.setattr(probes, "ping_redis", redis)
    with client_for(configured()) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "healthy", "redis": "healthy"},
    }
    database.assert_awaited_once()
    redis.assert_awaited_once()


@pytest.mark.parametrize("failed_dependency", ["database", "redis"])
def test_readiness_failure_is_sanitized(monkeypatch, caplog, failed_dependency):
    for name in ("database", "redis"):
        mock = AsyncMock()
        if name == failed_dependency:
            mock.side_effect = RuntimeError("redis://:private-password@host/0")
        monkeypatch.setattr(probes, f"ping_{name}", mock)
    with caplog.at_level(logging.WARNING, logger="movie.readiness"):
        result = asyncio.run(probes.check_readiness(configured()))
    assert result[failed_dependency] == "unavailable"
    assert "private-password" not in caplog.text
    with client_for(configured()) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert "private-password" not in response.text


def test_probe_timeout_fails_readiness(monkeypatch):
    cancelled = []

    async def slow_probe(url, timeout):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)

    monkeypatch.setattr(probes, "ping_database", slow_probe)
    monkeypatch.setattr(probes, "ping_redis", AsyncMock())
    result = asyncio.run(probes.check_readiness(configured(readiness_timeout_seconds=0.1)))
    assert result == {"database": "unavailable", "redis": "healthy"}
    assert cancelled == [True]


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_deployed_settings_require_explicit_services(environment):
    with pytest.raises(ValidationError):
        settings(environment=environment)


def test_deployed_settings_reject_placeholder_passwords():
    with pytest.raises(ValidationError):
        settings(
            environment="production",
            database_url="postgresql://movie:replace-local-password@db/movie",
            redis_url="redis://:secret@cache/0",
        )
    assert configured(environment="production").environment == "production"


@pytest.mark.parametrize("url", ["sqlite:///movie.db", "postgresql:///movie", "https://db"])
def test_invalid_database_url_rejected(url):
    with pytest.raises(ValidationError):
        settings(database_url=url)


@pytest.mark.parametrize("timeout", [0, -1, 11])
def test_probe_timeout_is_bounded(timeout):
    with pytest.raises(ValidationError):
        settings(readiness_timeout_seconds=timeout)


def test_environment_overrides_dotenv(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("APP_ENVIRONMENT=development\nAPP_LOG_LEVEL=WARNING\n")
    monkeypatch.setenv("APP_LOG_LEVEL", "ERROR")
    result = Settings(_env_file=env_file)
    assert result.environment == "test"
    assert result.log_level == "ERROR"


def test_settings_repr_masks_credentials():
    assert "private-password" not in repr(configured())


def test_json_formatter_excludes_unapproved_sensitive_fields():
    record = logging.LogRecord("movie.api", logging.INFO, "", 0, "request_completed", (), None)
    record.request_id = "trace-id"
    record.status_code = 200
    record.database_url = "postgresql://secret:password@db/movie"
    record.body = "sensitive request data"
    output = JsonFormatter().format(record)
    data = json.loads(output)
    assert data["event"] == "request_completed"
    assert data["request_id"] == "trace-id"
    assert data["status_code"] == 200
    assert "password" not in output
    assert "sensitive" not in output


def test_probe_clients_release_resources(monkeypatch):
    client = AsyncMock()
    client.ping.return_value = True
    monkeypatch.setattr(probes.Redis, "from_url", lambda *args, **kwargs: client)
    asyncio.run(probes.ping_redis("redis://localhost", 1))
    client.aclose.assert_awaited_once()


def test_redis_failure_still_closes_client(monkeypatch):
    client = AsyncMock()
    client.ping.side_effect = ConnectionError("test failure")
    monkeypatch.setattr(probes.Redis, "from_url", lambda *args, **kwargs: client)
    with pytest.raises(ConnectionError):
        asyncio.run(probes.ping_redis("redis://localhost", 1))
    client.aclose.assert_awaited_once()


def test_worker_ping_is_local_and_json_only(monkeypatch):
    import importlib

    import app.core.settings as settings_module

    monkeypatch.setattr(settings_module, "get_settings", lambda: configured())
    worker = importlib.import_module("app.workers.celery_app")
    assert worker.ping.run() == {"status": "ok"}
    assert worker.celery_app.conf.accept_content == ["json"]
    assert worker.celery_app.conf.task_serializer == "json"
    assert worker.celery_app.conf.task_time_limit == 300


def test_unhandled_error_returns_safe_response(monkeypatch):
    from unittest.mock import Mock

    from fastapi import Request

    import app.main as main_module

    async def failing_handler(request):
        raise RuntimeError("secret-credential")

    logger = Mock()
    monkeypatch.setattr(main_module, "logger", logger)
    request = Request({"type": "http", "method": "GET", "path": "/"})
    response = asyncio.run(main_module.request_logging(request, failing_handler))
    assert response.status_code == 500
    assert response.body == b'{"detail":"Internal server error"}'
    UUID(response.headers["X-Request-ID"])
    assert "secret-credential" not in str(logger.mock_calls)
