import os

import pytest
from fastapi.testclient import TestClient

from app.core.settings import Settings, get_settings
from app.main import app


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_SERVICE_TESTS") != "1", reason="Requires real PostgreSQL and Redis"
)
def test_real_service_readiness():
    # Fixture clears environment for unit isolation, so integration URLs are captured below.
    config = Settings(
        _env_file=None, environment="test", database_url=DATABASE_URL, redis_url=REDIS_URL
    )
    app.dependency_overrides[get_settings] = lambda: config
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 200, response.text
    assert response.json()["checks"] == {"database": "healthy", "redis": "healthy"}


DATABASE_URL = os.getenv(
    "APP_DATABASE_URL", "postgresql://movie:replace-local-password@localhost/movie"
)
REDIS_URL = os.getenv("APP_REDIS_URL", "redis://localhost:6379/0")
