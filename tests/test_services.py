import os

import pytest
from fastapi.testclient import TestClient

from app.core.settings import get_settings
from app.main import app


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_SERVICE_TESTS") != "1", reason="Requires real PostgreSQL and Redis"
)
def test_real_service_readiness(service_settings):
    app.dependency_overrides[get_settings] = lambda: service_settings
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 200, response.text
    assert response.json()["checks"] == {"database": "healthy", "redis": "healthy"}
