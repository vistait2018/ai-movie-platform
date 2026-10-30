import pytest

from app.core.settings import get_settings
from app.main import app


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
