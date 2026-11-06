import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.passwords import verify_password
from app.core.settings import Settings, get_settings
from app.db.session import get_db_session
from app.dev_outbox import local_messages
from app.main import app
from app.models.identity import AccessGrant, AuthAction, EmailOutbox, SecurityEvent, User, UserRole
from app.services import email_delivery, rate_limits
from app.services.email_delivery import DeliveryUnavailable
from app.services.identity_actions import digest_action, redeem_action, request_action
from app.services.rate_limits import (
    limit_action_confirmation,
    limit_action_request,
    limit_login,
    limit_registration,
    limit_reset_confirmation,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def require_services():
    if os.getenv("RUN_SERVICE_TESTS") != "1":
        pytest.skip("Requires isolated real PostgreSQL")


@pytest.fixture
def action_settings(service_settings):
    return Settings(
        _env_file=None,
        environment="test",
        database_url=service_settings.database_url,
        redis_url=service_settings.redis_url,
        access_signing_key=SecretStr(token_urlsafe(48)),
    )


@pytest.fixture
def action_client(identity_engine, action_settings):
    def database():
        with Session(identity_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_settings] = lambda: action_settings
    app.dependency_overrides[get_db_session] = database
    for dependency in (
        limit_registration,
        limit_login,
        limit_action_request,
        limit_action_confirmation,
        limit_reset_confirmation,
    ):
        app.dependency_overrides[dependency] = lambda: None
    with TestClient(app) as client:
        yield client


@pytest.fixture
def pending(action_client):
    data = {
        "email": uuid4().hex + "@example.com",
        "password": token_urlsafe(30),
        "display_name": "Viewer",
    }
    assert action_client.post("/api/v1/auth/register", json=data).status_code == 202
    return data


def message(engine, settings, email, purpose):
    with Session(engine) as session:
        messages = local_messages(session, email, settings, confirmed=True)
    return next(item for item in messages if item["purpose"] == purpose)


def activate(client, engine, settings, data):
    token = message(engine, settings, data["email"], "verify_email")["token"]
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    return token


def recovery(client, engine, settings, data):
    assert (
        client.post("/api/v1/auth/forgot-password", json={"email": data["email"]}).status_code
        == 202
    )
    return message(engine, settings, data["email"], "reset_password")["token"]


def test_registration_outbox_encrypted_and_verification(
    action_client, pending, identity_engine, action_settings, caplog
):
    email = pending["email"]
    value = message(identity_engine, action_settings, email, "verify_email")
    token = value["token"]
    assert len(token) == 43
    assert value["confirmation_endpoint"] == "/api/v1/auth/verify-email"
    with Session(identity_engine) as session:
        action = session.scalar(select(AuthAction).where(AuthAction.recipient == email))
        outbox = session.scalar(select(EmailOutbox).where(EmailOutbox.action_id == action.id))
        assert action.token_digest == digest_action("verify_email", token)
        assert token not in action.token_digest and token.encode() not in outbox.encrypted_payload
        assert email.encode() not in outbox.encrypted_payload
        assert action.consumed_at is None and action.expires_at > datetime.now(UTC)
    credentials = {"email": email, "password": pending["password"]}
    assert action_client.post("/api/v1/auth/login", json=credentials).status_code == 401
    assert action_client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    response = action_client.post("/api/v1/auth/login", json=credentials)
    assert response.status_code == 200
    access = response.json()["access_token"]
    assert action_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer " + access}
    ).json()["roles"] == ["viewer"]
    assert action_client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400
    with Session(identity_engine) as session:
        assert local_messages(session, email, action_settings, confirmed=True) == []
    assert (
        token not in caplog.text
        and pending["password"] not in caplog.text
        and access not in caplog.text
    )


def test_password_reset_revokes_all_grants_and_replay(
    action_client, pending, identity_engine, action_settings
):
    activate(action_client, identity_engine, action_settings, pending)
    credentials = {"email": pending["email"], "password": pending["password"]}
    tokens = [
        action_client.post("/api/v1/auth/login", json=credentials).json()["access_token"]
        for _ in range(2)
    ]
    value = recovery(action_client, identity_engine, action_settings, pending)
    password = token_urlsafe(32)
    assert (
        action_client.post(
            "/api/v1/auth/reset-password", json={"token": value, "new_password": password}
        ).status_code
        == 200
    )
    assert (
        action_client.post(
            "/api/v1/auth/reset-password", json={"token": value, "new_password": token_urlsafe(32)}
        ).status_code
        == 400
    )
    assert action_client.post("/api/v1/auth/login", json=credentials).status_code == 401
    assert (
        action_client.post(
            "/api/v1/auth/login", json=dict(credentials, password=password)
        ).status_code
        == 200
    )
    for token in tokens:
        assert (
            action_client.get(
                "/api/v1/auth/me", headers={"Authorization": "Bearer " + token}
            ).status_code
            == 401
        )
    with Session(identity_engine) as session:
        user = session.scalar(select(User).where(User.email == pending["email"]))
        assert user.status == "active" and verify_password(password, user.password_hash)
        assert user.password_hash.startswith("$argon2id$")
        assert (
            session.scalar(
                select(func.count())
                .select_from(AccessGrant)
                .where(AccessGrant.user_id == user.id, AccessGrant.revoked_at.is_not(None))
            )
            == 2
        )
        assert (
            session.scalar(
                select(SecurityEvent).where(
                    SecurityEvent.subject_user_id == user.id,
                    SecurityEvent.event == "reset_password_completed",
                )
            )
            is not None
        )


@pytest.mark.parametrize("purpose", ["verify_email", "reset_password"])
@pytest.mark.parametrize(
    "condition", ["expired", "wrong", "suspended", "deactivated", "changed_email"]
)
def test_invalid_and_ineligible_redemption(
    action_client, pending, identity_engine, action_settings, purpose, condition
):
    if purpose == "reset_password":
        activate(action_client, identity_engine, action_settings, pending)
        value = recovery(action_client, identity_engine, action_settings, pending)
    else:
        value = message(identity_engine, action_settings, pending["email"], purpose)["token"]
    with Session(identity_engine) as session, session.begin():
        user = session.scalar(select(User).where(User.email == pending["email"]))
        original_hash = user.password_hash
        original_status = user.status
        action = session.scalar(
            select(AuthAction).where(AuthAction.token_digest == digest_action(purpose, value))
        )
        if condition == "expired":
            action.created_at = datetime.now(UTC) - timedelta(hours=2)
            action.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif condition in {"suspended", "deactivated"}:
            user.status = condition
        elif condition == "changed_email":
            user.email = uuid4().hex + "@example.com"
        user_id = user.id
    body = {"token": token_urlsafe(32) if condition == "wrong" else value}
    endpoint = "/api/v1/auth/verify-email"
    if purpose == "reset_password":
        endpoint = "/api/v1/auth/reset-password"
        body["new_password"] = token_urlsafe(32)
    response = action_client.post(endpoint, json=body)
    assert response.status_code == 400 and response.json() == {
        "detail": "Invalid or expired action"
    }
    with Session(identity_engine) as session:
        user = session.get(User, user_id)
        assert user.password_hash == original_hash
        assert user.status == (
            condition if condition in {"suspended", "deactivated"} else original_status
        )


def test_tokens_purpose_bound_no_cross_account_override(
    action_client, pending, identity_engine, action_settings
):
    value = message(identity_engine, action_settings, pending["email"], "verify_email")["token"]
    assert (
        action_client.post(
            "/api/v1/auth/reset-password", json={"token": value, "new_password": token_urlsafe(32)}
        ).status_code
        == 400
    )
    for injected in (
        {"user_id": str(uuid4())},
        {"email": "other@example.com"},
        {"status": "active"},
        {"role": "admin"},
    ):
        assert (
            action_client.post(
                "/api/v1/auth/verify-email", json={"token": value} | injected
            ).status_code
            == 422
        )
    with Session(identity_engine) as session:
        user = session.scalar(select(User).where(User.email == pending["email"]))
        assert user.status == "pending" and user.email_verified_at is None
        assert (
            session.scalar(
                select(func.count()).select_from(UserRole).where(UserRole.user_id == user.id)
            )
            == 1
        )


@pytest.mark.parametrize("purpose", ["verify_email", "reset_password"])
def test_concurrent_redemption_single_winner(
    action_client, pending, identity_engine, action_settings, purpose
):
    if purpose == "reset_password":
        activate(action_client, identity_engine, action_settings, pending)
        value = recovery(action_client, identity_engine, action_settings, pending)
    else:
        value = message(identity_engine, action_settings, pending["email"], purpose)["token"]

    def redeem(_):
        with Session(identity_engine) as session:
            return redeem_action(
                session, value, purpose, token_urlsafe(32) if purpose == "reset_password" else None
            )

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sorted(pool.map(redeem, range(4))) == [False, False, False, True]


@pytest.mark.parametrize(
    "purpose,endpoint",
    [("verify_email", "request-verification"), ("reset_password", "forgot-password")],
)
def test_duplicate_requests_coalesced_and_replacement(
    action_client, pending, identity_engine, action_settings, purpose, endpoint
):
    if purpose == "reset_password":
        activate(action_client, identity_engine, action_settings, pending)
        old = recovery(action_client, identity_engine, action_settings, pending)
    else:
        old = message(identity_engine, action_settings, pending["email"], purpose)["token"]
    for _ in range(2):
        assert (
            action_client.post(
                "/api/v1/auth/" + endpoint, json={"email": pending["email"]}
            ).status_code
            == 202
        )
    assert message(identity_engine, action_settings, pending["email"], purpose)["token"] == old
    with Session(identity_engine) as session, session.begin():
        action = session.scalar(
            select(AuthAction).where(AuthAction.token_digest == digest_action(purpose, old))
        )
        action.created_at -= timedelta(seconds=120)
    assert (
        action_client.post("/api/v1/auth/" + endpoint, json={"email": pending["email"]}).status_code
        == 202
    )
    assert message(identity_engine, action_settings, pending["email"], purpose)["token"] != old
    with Session(identity_engine) as session:
        assert not redeem_action(
            session, old, purpose, token_urlsafe(32) if purpose == "reset_password" else None
        )


@pytest.mark.parametrize("endpoint", ["request-verification", "forgot-password"])
def test_requests_generic_and_status_restricted(
    action_client, pending, identity_engine, action_settings, endpoint
):
    known = action_client.post("/api/v1/auth/" + endpoint, json={"email": pending["email"]})
    unknown = action_client.post(
        "/api/v1/auth/" + endpoint, json={"email": uuid4().hex + "@example.com"}
    )
    assert known.status_code == unknown.status_code == 202 and known.json() == unknown.json()
    with Session(identity_engine) as session, session.begin():
        user = session.scalar(select(User).where(User.email == pending["email"]))
        user.status = "suspended"
        user_id = user.id
    suspended = action_client.post("/api/v1/auth/" + endpoint, json={"email": pending["email"]})
    assert suspended.json() == unknown.json()
    if endpoint == "forgot-password":
        with Session(identity_engine) as session:
            assert (
                session.scalar(
                    select(AuthAction).where(
                        AuthAction.user_id == user_id, AuthAction.kind == "reset_password"
                    )
                )
                is None
            )


@pytest.mark.parametrize("purpose", ["verify_email", "reset_password"])
def test_redemption_rolls_back_on_audit_failure(
    action_client, pending, identity_engine, action_settings, monkeypatch, purpose
):
    if purpose == "reset_password":
        activate(action_client, identity_engine, action_settings, pending)
        value = recovery(action_client, identity_engine, action_settings, pending)
        access = action_client.post(
            "/api/v1/auth/login", json={"email": pending["email"], "password": pending["password"]}
        ).json()["access_token"]
    else:
        value = message(identity_engine, action_settings, pending["email"], purpose)["token"]
    original = Session.add

    def fail(self, instance, **kwargs):
        if isinstance(instance, SecurityEvent):
            raise SQLAlchemyError("private credential-like failure details")
        return original(self, instance, **kwargs)

    monkeypatch.setattr(Session, "add", fail)
    endpoint = (
        "/api/v1/auth/verify-email" if purpose == "verify_email" else "/api/v1/auth/reset-password"
    )
    body = {"token": value}
    if purpose == "reset_password":
        body["new_password"] = token_urlsafe(32)
    response = action_client.post(endpoint, json=body)
    assert response.status_code == 503 and "private" not in response.text
    with Session(identity_engine) as session:
        action = session.scalar(
            select(AuthAction).where(AuthAction.token_digest == digest_action(purpose, value))
        )
        assert action.consumed_at is None
        assert (
            session.scalar(select(EmailOutbox).where(EmailOutbox.action_id == action.id))
            is not None
        )
        user = session.get(User, action.user_id)
        assert verify_password(pending["password"], user.password_hash)
        if purpose == "verify_email":
            assert user.status == "pending" and user.email_verified_at is None
    if purpose == "reset_password":
        assert (
            action_client.get(
                "/api/v1/auth/me", headers={"Authorization": "Bearer " + access}
            ).status_code
            == 200
        )


def test_delivery_failure_rolls_back_registration(
    action_client, pending, identity_engine, monkeypatch
):
    def fail(self, *args):
        raise DeliveryUnavailable("private delivery details")

    monkeypatch.setattr(email_delivery.DevelopmentOutbox, "enqueue", fail)
    data = dict(pending, email=uuid4().hex + "@example.com")
    response = action_client.post("/api/v1/auth/register", json=data)
    assert response.status_code == 503 and "private" not in response.text
    with Session(identity_engine) as session:
        assert session.scalar(select(User).where(User.email == data["email"])) is None


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_outbox_and_delivery_forbidden_outside_development(action_settings, environment):
    settings = action_settings.model_copy(update={"environment": environment})
    with pytest.raises(ValueError):
        local_messages(None, "viewer@example.com", settings, confirmed=True)
    with pytest.raises(DeliveryUnavailable):
        email_delivery.get_delivery(settings)
    assert not any("outbox" in route for route in app.openapi()["paths"])


def test_reset_validation_redacted(action_client, pending, identity_engine, action_settings):
    activate(action_client, identity_engine, action_settings, pending)
    value = recovery(action_client, identity_engine, action_settings, pending)
    response = action_client.post(
        "/api/v1/auth/reset-password", json={"token": value, "new_password": "short"}
    )
    assert response.status_code == 422
    assert value not in response.text and "short" not in response.text
    assert all("input" not in error and "ctx" not in error for error in response.json()["detail"])


def test_real_redis_action_limits(service_settings, action_settings, monkeypatch):
    from hashlib import sha256

    client = Redis.from_url(service_settings.redis_url.get_secret_value())
    monkeypatch.setattr(rate_limits, "get_registration_redis", lambda: client)
    settings = action_settings.model_copy(update={"action_requests_per_window": 1})
    address = "action-test-" + uuid4().hex
    identity = uuid4().hex + "@example.com"
    path = "/api/v1/auth/forgot-password"
    scope = sha256(path.encode()).hexdigest()
    request = Request({"type": "http", "path": path, "client": (address, 1), "headers": []})
    keys = [
        "auth:action:" + scope + ":" + kind + ":" + sha256(value.encode()).hexdigest()
        for kind, value in [("ip", address), ("identity", identity)]
    ]
    try:
        rate_limits.check_action_limits(request, identity, settings, 1)
        with pytest.raises(HTTPException) as caught:
            rate_limits.check_action_limits(request, identity, settings, 1)
        assert caught.value.status_code == 429 and 0 < client.ttl(keys[0]) <= 300
    finally:
        client.delete(*keys)
        client.close()


def test_concurrent_requests_coalesce(action_client, pending, identity_engine, action_settings):
    activate(action_client, identity_engine, action_settings, pending)

    def request(_):
        with Session(identity_engine) as session:
            request_action(session, pending["email"], "reset_password", action_settings)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(request, range(4)))
    with Session(identity_engine) as session:
        user = session.scalar(select(User).where(User.email == pending["email"]))
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuthAction)
                .where(
                    AuthAction.user_id == user.id,
                    AuthAction.kind == "reset_password",
                    AuthAction.consumed_at.is_(None),
                )
            )
            == 1
        )


def test_resend_failure_preserves_previous_action(
    action_client, pending, identity_engine, action_settings, monkeypatch
):
    value = message(identity_engine, action_settings, pending["email"], "verify_email")["token"]
    with Session(identity_engine) as session, session.begin():
        action = session.scalar(
            select(AuthAction).where(
                AuthAction.token_digest == digest_action("verify_email", value)
            )
        )
        action.created_at -= timedelta(seconds=120)

    def fail(self, *args):
        raise DeliveryUnavailable("private delivery error")

    monkeypatch.setattr(email_delivery.DevelopmentOutbox, "enqueue", fail)
    response = action_client.post(
        "/api/v1/auth/request-verification", json={"email": pending["email"]}
    )
    assert response.status_code == 503
    assert (
        message(identity_engine, action_settings, pending["email"], "verify_email")["token"]
        == value
    )
    assert action_client.post("/api/v1/auth/verify-email", json={"token": value}).status_code == 200


@pytest.mark.parametrize("change", ["unconfirmed", "remote", "wrong_key"])
def test_outbox_access_guards(action_client, pending, identity_engine, action_settings, change):
    from cryptography.fernet import Fernet, InvalidToken

    settings = action_settings
    if change == "remote":
        settings = settings.model_copy(
            update={"database_url": SecretStr("postgresql://remote.invalid/movie")}
        )
    elif change == "wrong_key":
        settings = settings.model_copy(
            update={"email_outbox_key": SecretStr(Fernet.generate_key().decode())}
        )
    with Session(identity_engine) as session, pytest.raises((ValueError, InvalidToken)):
        local_messages(session, pending["email"], settings, confirmed=change != "unconfirmed")


@pytest.mark.parametrize("key", [None, "invalid"])
def test_unconfigured_delivery_generic(action_client, pending, action_settings, key):
    settings = action_settings.model_copy(
        update={"email_outbox_key": SecretStr(key) if key else None}
    )
    app.dependency_overrides[get_settings] = lambda: settings
    for email in (pending["email"], uuid4().hex + "@example.com"):
        response = action_client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert response.status_code == 503 and response.json() == {
            "detail": "Authentication temporarily unavailable"
        }


def test_action_rate_limit_dependency_fails_closed(action_client, pending, monkeypatch):
    from redis.exceptions import ConnectionError

    class Broken:
        def eval(self, *args):
            raise ConnectionError("private infrastructure error")

    monkeypatch.setattr(rate_limits, "get_registration_redis", lambda: Broken())
    del app.dependency_overrides[limit_action_request]
    del app.dependency_overrides[limit_action_confirmation]
    del app.dependency_overrides[limit_reset_confirmation]
    for endpoint, payload in [
        ("forgot-password", {"email": pending["email"]}),
        ("verify-email", {"token": token_urlsafe(32)}),
        ("reset-password", {"token": token_urlsafe(32), "new_password": token_urlsafe(32)}),
    ]:
        response = action_client.post("/api/v1/auth/" + endpoint, json=payload)
        assert response.status_code == 503 and "private" not in response.text


@pytest.mark.parametrize("purpose", ["verify_email", "reset_password"])
def test_status_change_does_not_activate_or_restore(
    action_client, pending, identity_engine, action_settings, purpose
):
    if purpose == "reset_password":
        activate(action_client, identity_engine, action_settings, pending)
        value = recovery(action_client, identity_engine, action_settings, pending)
        status = "pending"
    else:
        value = message(identity_engine, action_settings, pending["email"], purpose)["token"]
        status = "active"
    with Session(identity_engine) as session, session.begin():
        user = session.scalar(select(User).where(User.email == pending["email"]))
        user.status = status
        user.email_verified_at = datetime.now(UTC) if status == "active" else None
    with Session(identity_engine) as session:
        assert not redeem_action(
            session, value, purpose, token_urlsafe(32) if purpose == "reset_password" else None
        )
