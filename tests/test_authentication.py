import os
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.core.tokens import encode_access
from app.db.session import get_db_session
from app.dev_verify import verify_local_user
from app.main import app
from app.models.identity import AccessGrant, SecurityEvent, User
from app.schemas.auth import LoginRequest
from app.services import rate_limits
from app.services.rate_limits import limit_login, limit_registration

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def require_services():
    if os.getenv("RUN_SERVICE_TESTS") != "1":
        pytest.skip("Requires isolated real PostgreSQL")


@pytest.fixture
def auth_settings(service_settings):
    return Settings(
        _env_file=None,
        environment="test",
        database_url=service_settings.database_url,
        redis_url=service_settings.redis_url,
        access_signing_key=SecretStr(token_urlsafe(48)),
    )


@pytest.fixture
def auth_client(identity_engine, auth_settings):
    def database():
        with Session(identity_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_settings] = lambda: auth_settings
    app.dependency_overrides[get_db_session] = database
    app.dependency_overrides[limit_registration] = lambda: None
    app.dependency_overrides[limit_login] = lambda: None
    with TestClient(app) as client:
        yield client


@pytest.fixture
def account(auth_client, identity_engine, auth_settings):
    data = {
        "email": f"auth-{uuid4().hex}@example.com",
        "display_name": "Viewer",
        "password": token_urlsafe(30),
    }
    assert auth_client.post("/api/v1/auth/register", json=data).status_code == 202
    with Session(identity_engine) as session:
        verify_local_user(session, data["email"], auth_settings, confirmed=True)
    return {"email": data["email"], "password": data["password"]}


def login_token(client, account):
    response = client.post("/api/v1/auth/login", json=account)
    assert response.status_code == 200
    return response.json()["access_token"]


def test_verified_login_me_and_redacted_audit(
    auth_client, account, identity_engine, auth_settings, caplog
):
    response = auth_client.post(
        "/api/v1/auth/login", json=dict(account, email=account["email"].upper())
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = response.json()
    assert set(result) == {"access_token", "token_type", "expires_in"}
    assert result["expires_in"] == 600 and result["token_type"] == "bearer"
    token = result["access_token"]
    claims = jwt.decode(
        token,
        auth_settings.access_signing_key.get_secret_value(),
        algorithms=["HS256"],
        issuer=auth_settings.access_token_issuer,
        audience=auth_settings.access_token_audience,
    )
    profile = auth_client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token})
    assert profile.status_code == 200
    assert profile.json() == {
        "id": claims["sub"],
        "email": account["email"],
        "display_name": "Viewer",
        "status": "active",
        "roles": ["viewer"],
    }
    assert profile.headers["cache-control"] == "no-store"
    with Session(identity_engine) as session:
        user = session.get(User, UUID(claims["sub"]))
        assert user.last_login_at is not None
        grant = session.get(AccessGrant, UUID(claims["jti"]))
        assert grant.user_id == user.id and grant.revoked_at is None
        events = session.scalars(
            select(SecurityEvent.event).where(SecurityEvent.subject_user_id == user.id)
        ).all()
        assert "login_succeeded" in events and "development_email_verified" in events
    assert token not in caplog.text and account["password"] not in caplog.text
    assert "password_hash" not in profile.text and "access_token" not in profile.text


@pytest.mark.parametrize("state", ["wrong", "unknown", "pending", "suspended", "deactivated"])
def test_ineligible_credentials_same_error(auth_client, account, identity_engine, state):
    data = dict(account)
    if state == "wrong":
        data["password"] = token_urlsafe(25)
    elif state == "unknown":
        data["email"] = f"missing-{uuid4().hex}@example.com"
    else:
        with Session(identity_engine) as session, session.begin():
            user = session.scalar(select(User).where(User.email == account["email"]))
            user.status = state
            if state == "pending":
                user.email_verified_at = None
    response = auth_client.post("/api/v1/auth/login", json=data)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}
    with Session(identity_engine) as session:
        user = session.scalar(select(User).where(User.email == account["email"]))
        assert (
            session.scalar(
                select(func.count()).select_from(AccessGrant).where(AccessGrant.user_id == user.id)
            )
            == 0
        )
        assert (
            session.scalar(select(SecurityEvent).where(SecurityEvent.event == "login_failed"))
            is not None
        )


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "garbage",
        "basic",
        "tampered",
        "expired",
        "issuer",
        "audience",
        "subject",
        "jti",
        "no_exp",
        "none_algorithm",
        "future",
        "type",
        "use",
        "long_lifetime",
        "string_exp",
    ],
)
def test_invalid_access_rejected(auth_client, account, auth_settings, kind):
    if kind == "missing":
        headers = {}
    elif kind == "basic":
        headers = {"Authorization": "Basic Zm9vOmJhcg=="}
    else:
        original = login_token(auth_client, account)
        claims = jwt.decode(original, options={"verify_signature": False})
        if kind == "garbage":
            token = "not-a-token"
        elif kind == "tampered":
            parts = original.split(".")
            parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
            token = ".".join(parts)
        else:
            algorithm = "HS256"
            typ = "at+jwt"
            if kind == "expired":
                claims.update(
                    iat=claims["iat"] - 1200, nbf=claims["nbf"] - 1200, exp=claims["exp"] - 1200
                )
            elif kind in {"issuer", "audience", "subject", "jti"}:
                claims[
                    {"issuer": "iss", "audience": "aud", "subject": "sub", "jti": "jti"}[kind]
                ] = "invalid"
            elif kind == "no_exp":
                del claims["exp"]
            elif kind == "none_algorithm":
                algorithm = "none"
            elif kind == "future":
                claims.update(
                    iat=claims["iat"] + 1200, nbf=claims["nbf"] + 1200, exp=claims["exp"] + 1200
                )
            elif kind == "type":
                typ = "JWT"
            elif kind == "use":
                claims["purpose"] = "refresh"
            elif kind == "long_lifetime":
                claims["exp"] += 600
            elif kind == "string_exp":
                claims["exp"] = str(claims["exp"])
            token = jwt.encode(
                claims,
                auth_settings.access_signing_key.get_secret_value() if algorithm != "none" else "",
                algorithm=algorithm,
                headers={"typ": typ},
            )
        headers = {"Authorization": "Bearer " + token}
    response = auth_client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("change", ["revoke", "suspend", "pending", "delete_grant", "db_expiry"])
def test_existing_token_obeys_database(auth_client, account, identity_engine, change):
    token = login_token(auth_client, account)
    claims = jwt.decode(token, options={"verify_signature": False})
    with Session(identity_engine) as session, session.begin():
        user = session.get(User, UUID(claims["sub"]))
        grant = session.get(AccessGrant, UUID(claims["jti"]))
        if change == "revoke":
            grant.revoked_at = datetime.now(UTC)
        elif change == "suspend":
            user.status = "suspended"
        elif change == "pending":
            user.status = "pending"
            user.email_verified_at = None
        elif change == "delete_grant":
            session.delete(grant)
        else:
            grant.expires_at += timedelta(seconds=1)
    assert (
        auth_client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token}).status_code
        == 401
    )


def test_signed_subject_cannot_access_another_user(auth_client, account, auth_settings):
    token = login_token(auth_client, account)
    claims = jwt.decode(token, options={"verify_signature": False})
    other = encode_access(
        uuid4(),
        UUID(claims["jti"]),
        datetime.fromtimestamp(claims["iat"], UTC),
        datetime.fromtimestamp(claims["exp"], UTC),
        auth_settings,
    )
    assert (
        auth_client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + other}).status_code
        == 401
    )
    assert app.openapi()["paths"]["/api/v1/auth/me"]["get"]["security"] == [{"HTTPBearer": []}]


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_dev_verification_forbidden(identity_engine, auth_settings, environment):
    # Guard runs before any SQL, even if a local-looking URL is supplied.
    settings = auth_settings.model_copy(update={"environment": environment})
    with Session(identity_engine) as session, pytest.raises(ValueError):
        verify_local_user(session, "nobody@example.com", settings, confirmed=True)


def test_dev_verification_does_not_reactivate_suspended(
    auth_client, account, identity_engine, auth_settings
):
    with Session(identity_engine) as session, session.begin():
        user = session.scalar(select(User).where(User.email == account["email"]))
        user.status = "suspended"
    with Session(identity_engine) as session, pytest.raises(ValueError):
        verify_local_user(session, account["email"], auth_settings, confirmed=True)


def test_missing_signing_key_fails_closed(auth_client, account, auth_settings):
    app.dependency_overrides[get_settings] = lambda: auth_settings.model_copy(
        update={"access_signing_key": None}
    )
    assert auth_client.post("/api/v1/auth/login", json=account).status_code == 503


@pytest.mark.parametrize("dimension", ["ip", "account"])
def test_real_redis_login_limits(service_settings, monkeypatch, auth_settings, dimension):
    from hashlib import sha256

    client = Redis.from_url(service_settings.redis_url.get_secret_value())
    monkeypatch.setattr(rate_limits, "get_registration_redis", lambda: client)
    settings = auth_settings.model_copy(update={"login_requests_per_window": 1})
    address = "isolated-login-" + uuid4().hex
    email = uuid4().hex + "@example.com"
    second_address = address if dimension == "ip" else address + "2"
    second_email = email if dimension == "account" else "other-" + email
    keys = [
        "auth:login:" + kind + ":" + sha256(value.encode()).hexdigest()
        for kind, value in [
            ("ip", address),
            ("ip", second_address),
            ("account", email),
            ("account", second_email),
        ]
    ]
    try:
        rate_limits.limit_login(
            LoginRequest(email=email, password="password"),
            Request({"type": "http", "client": (address, 1)}),
            settings,
        )
        with pytest.raises(HTTPException) as caught:
            rate_limits.limit_login(
                LoginRequest(email=second_email, password="password"),
                Request({"type": "http", "client": (second_address, 1)}),
                settings,
            )
        assert caught.value.status_code == 429
        assert caught.value.headers["Retry-After"] == "60"
        assert 0 < client.ttl(keys[0]) <= 60
    finally:
        client.delete(*keys)
        client.close()


def test_login_redis_failure_closed(auth_client, account, monkeypatch):
    from redis.exceptions import ConnectionError

    class Broken:
        def eval(self, *args):
            raise ConnectionError("private infrastructure detail")

    monkeypatch.setattr(rate_limits, "get_registration_redis", lambda: Broken())
    del app.dependency_overrides[limit_login]
    response = auth_client.post("/api/v1/auth/login", json=account)
    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication temporarily unavailable"}


def test_login_transaction_rolls_back_on_audit_failure(
    auth_client, account, identity_engine, monkeypatch
):
    from sqlalchemy.exc import SQLAlchemyError

    original = Session.add

    def fail_audit(self, instance, **kwargs):
        if isinstance(instance, SecurityEvent):
            raise SQLAlchemyError("private audit infrastructure detail")
        return original(self, instance, **kwargs)

    monkeypatch.setattr(Session, "add", fail_audit)
    response = auth_client.post("/api/v1/auth/login", json=account)
    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication temporarily unavailable"}
    with Session(identity_engine) as session:
        user = session.scalar(select(User).where(User.email == account["email"]))
        assert user.last_login_at is None
        assert (
            session.scalar(
                select(func.count()).select_from(AccessGrant).where(AccessGrant.user_id == user.id)
            )
            == 0
        )


@pytest.mark.parametrize("change", ["unconfirmed", "remote"])
def test_dev_verification_requires_local_confirmation(identity_engine, auth_settings, change):
    if change == "remote":
        auth_settings = auth_settings.model_copy(
            update={"database_url": SecretStr("postgresql://remote.invalid/movie")}
        )
    with Session(identity_engine) as session, pytest.raises(ValueError):
        verify_local_user(
            session, "nobody@example.com", auth_settings, confirmed=change != "unconfirmed"
        )


@pytest.mark.parametrize("key", [None, "short", "replace-" + "x" * 40])
def test_invalid_signing_configuration(auth_client, account, auth_settings, key):
    settings = auth_settings.model_copy(
        update={"access_signing_key": SecretStr(key) if key else None}
    )
    app.dependency_overrides[get_settings] = lambda: settings
    assert auth_client.post("/api/v1/auth/login", json=account).status_code == 503
