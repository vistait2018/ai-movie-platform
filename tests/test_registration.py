import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from app.core.passwords import verify_password
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.identity import Permission, Role, SecurityEvent, User, UserRole
from app.schemas.auth import RegistrationRequest
from app.services.rate_limits import limit_registration
from app.services.registration import register_user

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def require_services():
    if os.getenv("RUN_SERVICE_TESTS") != "1":
        pytest.skip("Requires isolated real PostgreSQL")


@pytest.fixture
def registration_client(identity_engine):
    def database():
        with Session(identity_engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = database
    app.dependency_overrides[limit_registration] = lambda: None
    with TestClient(app) as client:
        yield client


def payload():
    return {
        "email": f"viewer-{uuid4().hex}@example.com",
        "display_name": "Movie Viewer",
        "password": "A long movie passphrase 2026!",
    }


def test_register_persists_pending_viewer(registration_client, identity_engine):
    data = payload()
    data["email"] = "  " + data["email"].upper() + "  "
    response = registration_client.post("/api/v1/auth/register", json=data)
    assert response.status_code == 202
    assert set(response.json()) == {"message"}
    assert data["password"] not in response.text
    with Session(identity_engine) as session:
        user = session.scalar(select(User).where(User.email == data["email"].strip().casefold()))
        assert user is not None
        assert user.display_name == "Movie Viewer"
        assert user.status == "pending" and user.email_verified_at is None
        assert user.created_at.tzinfo is not None and user.updated_at.tzinfo is not None
        assert user.last_login_at is None
        assert user.password_hash.startswith("$argon2id$")
        assert verify_password(data["password"], user.password_hash)
        assert session.scalars(
            select(Role.code).join(UserRole).where(UserRole.user_id == user.id)
        ).all() == ["viewer"]
        assert (
            session.scalar(
                select(func.count())
                .select_from(SecurityEvent)
                .where(SecurityEvent.subject_user_id == user.id)
            )
            == 1
        )


def test_duplicate_response_and_password_unchanged(registration_client, identity_engine):
    data = payload()
    first = registration_client.post("/api/v1/auth/register", json=data)
    changed = dict(data, password="A different long passphrase 2026!")
    second = registration_client.post("/api/v1/auth/register", json=changed)
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    with Session(identity_engine) as session:
        users = session.scalars(select(User).where(User.email == data["email"])).all()
        assert len(users) == 1
        assert verify_password(data["password"], users[0].password_hash)
        assert not verify_password(changed["password"], users[0].password_hash)


@pytest.mark.parametrize(
    "extra",
    [
        {"role": "super_admin"},
        {"roles": ["admin"]},
        {"status": "active"},
        {"email_verified_at": "2026-01-01"},
        {"password_hash": "injected"},
    ],
)
def test_protected_fields_rejected(registration_client, identity_engine, extra):
    data = payload() | extra
    response = registration_client.post("/api/v1/auth/register", json=data)
    assert response.status_code == 422
    assert data["password"] not in response.text
    with Session(identity_engine) as session:
        assert session.scalar(select(User).where(User.email == data["email"])) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("email", "invalid"),
        ("display_name", "   "),
        ("password", "short"),
        ("password", " " * 15),
        ("password", "x" * 129),
    ],
)
def test_invalid_input_redacted(registration_client, field, value):
    data = payload()
    data[field] = value
    response = registration_client.post("/api/v1/auth/register", json=data)
    assert response.status_code == 422
    assert all("input" not in item and "ctx" not in item for item in response.json()["detail"])
    if field == "password":
        assert value not in response.text


def test_concurrent_duplicate_registration(identity_engine):
    request = RegistrationRequest(**payload())

    def create():
        with Session(identity_engine) as session:
            register_user(session, request)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: create(), range(4)))
    with Session(identity_engine) as session:
        users = session.scalars(select(User).where(User.email == str(request.email))).all()
        assert len(users) == 1
        assert (
            session.scalar(
                select(func.count()).select_from(UserRole).where(UserRole.user_id == users[0].id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(SecurityEvent)
                .where(SecurityEvent.subject_user_id == users[0].id)
            )
            == 1
        )


def test_metadata_matches_migration(identity_engine):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    with identity_engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    assert {
        "users",
        "roles",
        "permissions",
        "user_roles",
        "role_permissions",
        "security_events",
    } <= set(inspect(identity_engine).get_table_names())
    with Session(identity_engine) as session:
        assert {"viewer", "creator", "admin", "super_admin", "moderator", "finance_admin"} == set(
            session.scalars(select(Role.code))
        )
        assert session.scalar(select(func.count()).select_from(Permission)) == 9


def test_migration_round_trip(migration_engine):
    config = Config("alembic.ini")
    with migration_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        assert "users" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        command.check(config)
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0003_auth_actions_outbox"
        )


def test_database_failure_response_is_sanitized(registration_client, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    import app.api.auth as auth_api

    def fail(*args):
        raise SQLAlchemyError("private database address and password")

    monkeypatch.setattr(auth_api, "register_user", fail)
    response = registration_client.post("/api/v1/auth/register", json=payload())
    assert response.status_code == 503
    assert response.json() == {"detail": "Registration temporarily unavailable"}
    assert "private" not in response.text


def test_registration_transaction_rolls_back(identity_engine, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    request = RegistrationRequest(**payload())
    with Session(identity_engine) as session:

        def fail(*args):
            raise SQLAlchemyError("Simulated role/audit write failure")

        monkeypatch.setattr(session, "add", fail)
        with pytest.raises(SQLAlchemyError):
            register_user(session, request)
    with Session(identity_engine) as session:
        assert session.scalar(select(User).where(User.email == str(request.email))) is None


def test_real_redis_registration_limit(service_settings, monkeypatch):
    from hashlib import sha256

    from fastapi import HTTPException, Request
    from redis import Redis

    from app.core.settings import Settings
    from app.services import rate_limits

    client = Redis.from_url(service_settings.redis_url.get_secret_value())
    address = "isolated-test-" + uuid4().hex
    key = "auth:registration:" + sha256(address.encode()).hexdigest()
    monkeypatch.setattr(rate_limits, "get_registration_redis", lambda: client)
    request = Request({"type": "http", "client": (address, 1)})
    settings = Settings(_env_file=None, registration_requests_per_window=1)
    try:
        rate_limits.limit_registration(request, settings)
        with pytest.raises(HTTPException) as caught:
            rate_limits.limit_registration(request, settings)
        assert caught.value.status_code == 429
        assert 0 < client.ttl(key) <= 60
    finally:
        # Delete only the unique key created by this test, never flush existing Redis data.
        client.delete(key)
        client.close()
