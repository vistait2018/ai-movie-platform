import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.db.session import get_db_session
from app.dev_outbox import local_messages
from app.dev_verify import verify_local_user
from app.main import app
from app.models.identity import AccessGrant, AuthSession, RefreshCredential, SecurityEvent, User
from app.services.rate_limits import (
    limit_action_confirmation,
    limit_action_request,
    limit_login,
    limit_logout,
    limit_refresh,
    limit_registration,
    limit_reset_confirmation,
)
from app.services.sessions import refresh_digest, rotate_refresh

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def services_required():
    if os.getenv("RUN_SERVICE_TESTS") != "1":
        pytest.skip("Requires real PostgreSQL/Redis")


@pytest.fixture
def session_settings(service_settings):
    return Settings(
        _env_file=None,
        environment="test",
        database_url=service_settings.database_url,
        redis_url=service_settings.redis_url,
        access_signing_key=SecretStr(token_urlsafe(48)),
    )


@pytest.fixture
def session_client(identity_engine, session_settings):
    def database():
        with Session(identity_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db_session] = database
    app.dependency_overrides[get_settings] = lambda: session_settings
    for dependency in (
        limit_registration,
        limit_login,
        limit_refresh,
        limit_logout,
        limit_action_request,
        limit_action_confirmation,
        limit_reset_confirmation,
    ):
        app.dependency_overrides[dependency] = lambda: None
    with TestClient(app) as client:
        yield client


@pytest.fixture
def session_account(session_client, session_settings, identity_engine):
    data = {
        "email": uuid4().hex + "@example.com",
        "password": token_urlsafe(30),
        "display_name": "Session viewer",
    }
    assert session_client.post("/api/v1/auth/register", json=data).status_code == 202
    with Session(identity_engine) as session:
        verify_local_user(session, data["email"], session_settings, confirmed=True)
    return {"email": data["email"], "password": data["password"]}


def login(client, account, *, legacy=False):
    response = client.post(
        "/api/v1/auth/login", json=account if legacy else account | {"session_mode": "refresh"}
    )
    assert response.status_code == 200
    return response.json()


def headers(pair):
    return {"Authorization": "Bearer " + pair["access_token"]}


def refresh(client, pair):
    return client.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})


def test_login_compatibility_hash_storage_and_rotation(
    session_client, session_account, identity_engine, caplog
):
    legacy = login(session_client, session_account, legacy=True)
    assert set(legacy) == {"access_token", "expires_in", "token_type"}
    first = login(session_client, session_account)
    assert set(first) == set(legacy) | {"session_id", "refresh_token", "refresh_expires_in"}
    assert first["refresh_expires_in"] == 604800 and len(first["refresh_token"]) == 64
    response = refresh(session_client, first)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    second = response.json()
    assert (
        second["session_id"] == first["session_id"]
        and second["refresh_token"] != first["refresh_token"]
    )
    assert session_client.get("/api/v1/auth/me", headers=headers(first)).status_code == 401
    assert session_client.get("/api/v1/auth/me", headers=headers(second)).status_code == 200
    assert session_client.get("/api/v1/auth/me", headers=headers(legacy)).status_code == 200
    with Session(identity_engine) as session:
        rows = session.scalars(
            select(RefreshCredential).where(
                RefreshCredential.session_id == UUID(first["session_id"])
            )
        ).all()
        assert len(rows) == 2
        parent = next(row for row in rows if row.parent_id is None)
        child = next(row for row in rows if row.parent_id is not None)
        assert (
            parent.token_digest == refresh_digest(first["refresh_token"])
            and parent.consumed_at is not None
        )
        assert child.parent_id == parent.id and child.token_digest == refresh_digest(
            second["refresh_token"]
        )
        assert first["refresh_token"] not in str(parent.__dict__)
        assert second["refresh_token"] not in str(child.__dict__)
    assert first["refresh_token"] not in caplog.text and second["access_token"] not in caplog.text


def test_reuse_kills_successor_but_not_other_device(
    session_client, session_account, identity_engine
):
    first = login(session_client, session_account)
    other = login(session_client, session_account)
    successor = refresh(session_client, first).json()
    rejected = refresh(session_client, first)
    assert rejected.status_code == 401 and rejected.json() == {"detail": "Authentication required"}
    assert session_client.get("/api/v1/auth/me", headers=headers(successor)).status_code == 401
    assert refresh(session_client, successor).status_code == 401
    assert session_client.get("/api/v1/auth/me", headers=headers(other)).status_code == 200
    with Session(identity_engine) as session:
        family = session.get(AuthSession, UUID(first["session_id"]))
        assert family.revoked_at is not None and family.revoked_reason == "reuse"
        assert (
            session.scalar(
                select(SecurityEvent).where(
                    SecurityEvent.subject_user_id == family.user_id,
                    SecurityEvent.event == "refresh_reuse_detected",
                )
            )
            is not None
        )


def test_concurrent_refresh_one_successor_then_family_revocation(
    session_client, session_account, session_settings, identity_engine
):
    first = login(session_client, session_account)

    def rotate(_):
        with Session(identity_engine) as session:
            return rotate_refresh(session, first["refresh_token"], session_settings)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(rotate, range(4)))
    issued = [result for result in results if result is not None]
    assert len(issued) == 1
    successor = issued[0].model_dump(mode="json")
    assert session_client.get("/api/v1/auth/me", headers=headers(successor)).status_code == 401
    assert refresh(session_client, successor).status_code == 401
    with Session(identity_engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(RefreshCredential)
                .where(RefreshCredential.session_id == UUID(first["session_id"]))
            )
            == 2
        )


@pytest.mark.parametrize(
    "condition",
    [
        "token_expired",
        "session_expired",
        "token_revoked",
        "session_revoked",
        "suspended",
        "deactivated",
        "pending",
        "deleted",
        "family_deleted",
    ],
)
def test_ineligible_refresh_rejected(session_client, session_account, identity_engine, condition):
    pair = login(session_client, session_account)
    with Session(identity_engine) as session, session.begin():
        family = session.get(AuthSession, UUID(pair["session_id"]))
        user = session.get(User, family.user_id)
        credential = session.scalar(
            select(RefreshCredential).where(RefreshCredential.session_id == family.id)
        )
        now = datetime.now(UTC)
        if condition == "token_expired":
            credential.created_at = now - timedelta(days=2)
            credential.expires_at = now - timedelta(seconds=2)
        elif condition == "session_expired":
            family.created_at = now - timedelta(days=2)
            family.expires_at = now - timedelta(seconds=2)
        elif condition == "token_revoked":
            credential.revoked_at = now
        elif condition == "session_revoked":
            family.revoked_at = now
        elif condition in {"suspended", "deactivated", "pending"}:
            user.status = condition
            if condition == "pending":
                user.email_verified_at = None
        elif condition == "deleted":
            session.delete(user)
        else:
            session.delete(family)
    assert refresh(session_client, pair).status_code == 401
    assert session_client.get("/api/v1/auth/me", headers=headers(pair)).status_code == 401


@pytest.mark.parametrize("value", ["invalid", "random", "access"])
def test_invalid_refresh_sanitized(session_client, session_account, value):
    pair = login(session_client, session_account)
    token = (
        pair["access_token"]
        if value == "access"
        else token_urlsafe(48)
        if value == "random"
        else "invalid"
    )
    response = session_client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    assert response.status_code == 401 and response.json() == {"detail": "Authentication required"}
    assert token not in response.text


def test_logout_idempotent_current_family_only(session_client, session_account):
    first = login(session_client, session_account)
    other = login(session_client, session_account)
    for _ in range(2):
        response = session_client.post("/api/v1/auth/logout", headers=headers(first))
        assert response.status_code == 204 and response.content == b""
    assert refresh(session_client, first).status_code == 401
    assert session_client.get("/api/v1/auth/me", headers=headers(first)).status_code == 401
    assert session_client.get("/api/v1/auth/me", headers=headers(other)).status_code == 200


def test_logout_legacy_and_obsolete_rotation_token(session_client, session_account):
    legacy = login(session_client, session_account, legacy=True)
    assert session_client.post("/api/v1/auth/logout", headers=headers(legacy)).status_code == 204
    assert session_client.post("/api/v1/auth/logout", headers=headers(legacy)).status_code == 204
    first = login(session_client, session_account)
    successor = refresh(session_client, first).json()
    assert session_client.post("/api/v1/auth/logout", headers=headers(first)).status_code == 401
    assert session_client.get("/api/v1/auth/me", headers=headers(successor)).status_code == 200


def test_logout_all_across_devices_and_legacy(session_client, session_account, identity_engine):
    first = login(session_client, session_account)
    other = login(session_client, session_account)
    legacy = login(session_client, session_account, legacy=True)
    assert session_client.post("/api/v1/auth/logout-all", headers=headers(first)).status_code == 204
    for pair in (first, other, legacy):
        assert session_client.get("/api/v1/auth/me", headers=headers(pair)).status_code == 401
    for pair in (first, other):
        assert refresh(session_client, pair).status_code == 401
    assert session_client.post("/api/v1/auth/logout-all", headers=headers(first)).status_code == 401
    assert login(session_client, session_account)["refresh_token"]


def test_reset_revokes_sessions_and_old_refresh(
    session_client, session_account, session_settings, identity_engine
):
    first = login(session_client, session_account)
    second = login(session_client, session_account)
    legacy = login(session_client, session_account, legacy=True)
    assert (
        session_client.post(
            "/api/v1/auth/forgot-password", json={"email": session_account["email"]}
        ).status_code
        == 202
    )
    with Session(identity_engine) as session:
        message = next(
            m
            for m in local_messages(
                session, session_account["email"], session_settings, confirmed=True
            )
            if m["purpose"] == "reset_password"
        )
    password = token_urlsafe(30)
    body = {"token": message["token"], "new_password": password}
    assert session_client.post("/api/v1/auth/reset-password", json=body).status_code == 200
    assert session_client.post("/api/v1/auth/reset-password", json=body).status_code == 400
    for pair in (first, second, legacy):
        assert session_client.get("/api/v1/auth/me", headers=headers(pair)).status_code == 401
    for pair in (first, second):
        assert refresh(session_client, pair).status_code == 401
    assert session_client.post("/api/v1/auth/login", json=session_account).status_code == 401
    assert login(session_client, session_account | {"password": password})["refresh_token"]
    with Session(identity_engine) as session:
        family = session.get(AuthSession, UUID(first["session_id"]))
        assert family.revoked_reason == "password_reset"


@pytest.mark.parametrize("operation", ["refresh", "logout", "logout-all", "login"])
def test_transaction_failure_rolls_back(
    session_client, session_account, identity_engine, operation
):
    pair = login(session_client, session_account)

    def reject(session):
        raise SQLAlchemyError("private transaction details")

    event.listen(Session, "before_commit", reject)
    try:
        if operation == "refresh":
            response = refresh(session_client, pair)
        elif operation == "login":
            response = session_client.post(
                "/api/v1/auth/login", json=session_account | {"session_mode": "refresh"}
            )
        else:
            response = session_client.post("/api/v1/auth/" + operation, headers=headers(pair))
        assert response.status_code == 503 and "private" not in response.text
    finally:
        event.remove(Session, "before_commit", reject)
    assert session_client.get("/api/v1/auth/me", headers=headers(pair)).status_code == 200
    with Session(identity_engine) as session:
        row = session.scalar(
            select(RefreshCredential).where(
                RefreshCredential.token_digest == refresh_digest(pair["refresh_token"])
            )
        )
        assert row.consumed_at is None and row.revoked_at is None
        assert session.get(AuthSession, UUID(pair["session_id"])).revoked_at is None


def test_absolute_session_expiry_bounds_successors(
    session_client, session_account, identity_engine
):
    pair = login(session_client, session_account)
    with Session(identity_engine) as session, session.begin():
        family = session.get(AuthSession, UUID(pair["session_id"]))
        family.expires_at = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
    successor = refresh(session_client, pair).json()
    assert 0 < successor["refresh_expires_in"] <= 90
    assert successor["expires_in"] <= successor["refresh_expires_in"]


@pytest.mark.parametrize("endpoint", ["logout", "logout-all"])
def test_missing_invalid_logout_auth(session_client, endpoint):
    assert session_client.post("/api/v1/auth/" + endpoint).status_code == 401
    assert (
        session_client.post(
            "/api/v1/auth/" + endpoint, headers={"Authorization": "Bearer invalid"}
        ).status_code
        == 401
    )


def test_database_enforces_single_successor(session_client, session_account, identity_engine):
    pair = login(session_client, session_account)
    assert refresh(session_client, pair).status_code == 200
    with Session(identity_engine) as session:
        parent = session.scalar(
            select(RefreshCredential).where(
                RefreshCredential.token_digest == refresh_digest(pair["refresh_token"])
            )
        )
        values = {
            "session_id": parent.session_id,
            "parent_id": parent.id,
            "token_digest": refresh_digest(token_urlsafe(48)),
            "created_at": datetime.now(UTC),
            "expires_at": datetime.now(UTC) + timedelta(days=1),
        }
    with Session(identity_engine) as session, pytest.raises(IntegrityError):
        with session.begin():
            session.add(RefreshCredential(**values))


def test_audit_events_and_validation_redaction(
    session_client, session_account, identity_engine, caplog
):
    pair = login(session_client, session_account)
    response = session_client.post("/api/v1/auth/refresh", json={"refresh_token": "x" * 513})
    assert response.status_code == 422 and "x" * 513 not in response.text
    assert all("input" not in e and "ctx" not in e for e in response.json()["detail"])
    child = refresh(session_client, pair).json()
    assert refresh(session_client, pair).status_code == 401
    with Session(identity_engine) as session:
        family = session.get(AuthSession, UUID(pair["session_id"]))
        events = session.scalars(
            select(SecurityEvent.event).where(SecurityEvent.subject_user_id == family.user_id)
        ).all()
        assert {"refresh_rotated", "refresh_reuse_detected", "session_revoked_reuse"} <= set(events)
    for value in (
        pair["access_token"],
        pair["refresh_token"],
        child["access_token"],
        child["refresh_token"],
        session_account["password"],
    ):
        assert value not in caplog.text


def test_refresh_and_logout_redis_failure_closed(session_client, session_account, monkeypatch):
    from redis.exceptions import ConnectionError

    from app.services import rate_limits

    pair = login(session_client, session_account)

    class Broken:
        def eval(self, *args):
            raise ConnectionError("private redis infrastructure detail")

    monkeypatch.setattr(rate_limits, "get_registration_redis", lambda: Broken())
    del app.dependency_overrides[limit_refresh]
    del app.dependency_overrides[limit_logout]
    assert refresh(session_client, pair).status_code == 503
    response = session_client.post("/api/v1/auth/logout", headers=headers(pair))
    assert response.status_code == 503 and "private" not in response.text


def test_real_redis_refresh_throttle(session_settings, monkeypatch):
    from hashlib import sha256

    from fastapi import HTTPException, Request
    from redis import Redis

    from app.schemas.auth import RefreshRequest
    from app.services import rate_limits

    client = Redis.from_url(session_settings.redis_url.get_secret_value())
    monkeypatch.setattr(rate_limits, "get_registration_redis", lambda: client)
    settings = session_settings.model_copy(update={"session_requests_per_window": 1})
    address = "refresh-test-" + uuid4().hex
    value = token_urlsafe(48)
    path = "/api/v1/auth/refresh"
    scope = sha256(path.encode()).hexdigest()
    keys = [
        "auth:action:" + scope + ":" + kind + ":" + sha256(item.encode()).hexdigest()
        for kind, item in [("ip", address), ("identity", value)]
    ]
    request = Request({"type": "http", "path": path, "headers": [], "client": (address, 1)})
    try:
        rate_limits.limit_refresh(RefreshRequest(refresh_token=value), request, settings)
        with pytest.raises(HTTPException) as caught:
            rate_limits.limit_refresh(RefreshRequest(refresh_token=value), request, settings)
        assert caught.value.status_code == 429 and caught.value.headers["Retry-After"] == "60"
        assert 0 < client.ttl(keys[0]) <= 60
    finally:
        client.delete(*keys)
        client.close()


def test_password_reset_transaction_preserves_families_on_failure(
    session_client, session_account, session_settings, identity_engine
):
    pair = login(session_client, session_account)
    assert (
        session_client.post(
            "/api/v1/auth/forgot-password", json={"email": session_account["email"]}
        ).status_code
        == 202
    )
    with Session(identity_engine) as session:
        message = next(
            m
            for m in local_messages(
                session, session_account["email"], session_settings, confirmed=True
            )
            if m["purpose"] == "reset_password"
        )

    def reject(session):
        raise SQLAlchemyError("simulated reset commit failure")

    event.listen(Session, "before_commit", reject)
    try:
        response = session_client.post(
            "/api/v1/auth/reset-password",
            json={"token": message["token"], "new_password": token_urlsafe(30)},
        )
        assert response.status_code == 503
    finally:
        event.remove(Session, "before_commit", reject)
    assert session_client.get("/api/v1/auth/me", headers=headers(pair)).status_code == 200
    assert refresh(session_client, pair).status_code == 200


def test_revocation_of_existing_family_without_grant_update(
    session_client, session_account, identity_engine
):
    pair = login(session_client, session_account)
    with Session(identity_engine) as session, session.begin():
        session.get(AuthSession, UUID(pair["session_id"])).revoked_at = datetime.now(UTC)
    # Access authentication consults the session, not only the access grant's own timestamp.
    assert session_client.get("/api/v1/auth/me", headers=headers(pair)).status_code == 401


def test_upgrade_preserves_preexisting_user_and_legacy_grant(migration_engine):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    config = Config("alembic.ini")
    user_id, grant_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    with migration_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0004_smtp_deliveries")
        connection.execute(
            text(
                "INSERT INTO users (id,email,display_name,password_hash,status,email_verified_at) "
                "VALUES (:id,:email,'Legacy viewer','test fixture hash','active',:now)"
            ),
            {"id": user_id, "email": uuid4().hex + "@example.com", "now": now},
        )
        connection.execute(
            text(
                "INSERT INTO access_grants (id,user_id,created_at,expires_at) "
                "VALUES (:id,:user,:now,:expiry)"
            ),
            {"id": grant_id, "user": user_id, "now": now, "expiry": now + timedelta(minutes=10)},
        )
        command.upgrade(config, "head")
        with Session(connection) as session:
            grant = session.get(AccessGrant, grant_id)
            assert (
                grant.user_id == user_id and grant.session_id is None and grant.revoked_at is None
            )
            assert session.get(User, user_id).status == "active"
            assert session.scalar(select(func.count()).select_from(AuthSession)) == 0
        command.check(config)
