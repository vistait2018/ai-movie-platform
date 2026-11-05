import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import UUID

import jwt
import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_sessions import (
    session_account as session_account,
)
from test_sessions import (
    session_client as session_client,
)
from test_sessions import (
    session_settings as session_settings,
)

from app.core.browser import PATH, binding, cookie_name, csrf_key, validate_csrf
from app.core.settings import Settings, get_settings
from app.db.session import get_db_session
from app.dev_outbox import local_messages
from app.main import app
from app.models.identity import AuthSession, User
from app.services.rate_limits import limit_logout

ORIGIN = "http://127.0.0.1:8000"


def challenge(client):
    response = client.get(PATH + "/csrf")
    assert response.status_code == 200
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def browser_login(client, account):
    response = client.post(PATH + "/login", json=account, headers=challenge(client))
    assert response.status_code == 200
    assert set(response.json()) == {"authenticated", "session_id", "expires_in"}
    return response


@pytest.mark.integration
def test_browser_cookie_lifecycle_and_api_isolation(session_client, session_account, caplog):
    with caplog.at_level(logging.INFO):
        initial = challenge(session_client)
        bootstrap = session_client.cookies.get("movie_bootstrap")
        response = session_client.post(PATH + "/login", json=session_account, headers=initial)
        assert response.status_code == 200
        pair = dict(session_client.cookies)
        assert not session_client.cookies.get("movie_bootstrap")
        assert pair["movie_refresh"] != bootstrap
        for cookie in response.headers.get_list("set-cookie"):
            assert "HttpOnly" in cookie and "SameSite=lax" in cookie
            assert "Path=" + PATH in cookie and "Domain=" not in cookie
        assert session_client.get(PATH + "/session").json()["status"] == "active"
        assert session_client.get("/api/v1/auth/me").status_code == 401
        # A pre-login challenge cannot mutate the authenticated session.
        assert session_client.post(PATH + "/refresh", json={}, headers=initial).status_code == 403
        old_csrf = challenge(session_client)
        response = session_client.post(PATH + "/refresh", json={}, headers=old_csrf)
        assert response.status_code == 200
        assert session_client.cookies.get("movie_refresh") != pair["movie_refresh"]
        assert "refresh_token" not in response.json() and "access_token" not in response.json()
        assert session_client.post(PATH + "/logout", json={}, headers=old_csrf).status_code == 403
        response = session_client.post(PATH + "/logout", json={}, headers=challenge(session_client))
        assert response.status_code == 204
        assert all("Max-Age=0" in c for c in response.headers.get_list("set-cookie"))
        assert not dict(session_client.cookies)
        assert session_client.get(PATH + "/session").status_code == 401
    assert session_account["password"] not in caplog.text
    assert all(secret not in caplog.text for secret in pair.values())


@pytest.mark.integration
@pytest.mark.parametrize("operation", ["login", "refresh", "logout", "logout-all"])
@pytest.mark.parametrize("attack", ["missing", "invalid", "evil", "null", "suffix", "form"])
def test_csrf_rejects_before_authentication(session_client, operation, attack):
    headers = challenge(session_client)
    if attack == "missing":
        headers.pop("X-CSRF-Token")
    elif attack == "invalid":
        headers["X-CSRF-Token"] = token_urlsafe(32)
    elif attack in {"evil", "null", "suffix"}:
        headers["Origin"] = {
            "evil": "https://evil.example",
            "null": "null",
            "suffix": ORIGIN + ".evil.example",
        }[attack]
    if attack == "form":
        response = session_client.post(PATH + "/" + operation, data={"x": "y"}, headers=headers)
    else:
        response = session_client.post(PATH + "/" + operation, json={}, headers=headers)
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.integration
def test_csrf_expired_wrong_binding_and_referer(session_client, session_account, session_settings):
    headers = challenge(session_client)
    claims = jwt.decode(headers["X-CSRF-Token"], options={"verify_signature": False})
    claims.update(
        iat=int(datetime.now(UTC).timestamp()) - 1000, exp=int(datetime.now(UTC).timestamp()) - 1
    )
    headers["X-CSRF-Token"] = jwt.encode(
        claims, csrf_key(session_settings), algorithm="HS256", headers={"typ": "csrf+jwt"}
    )
    assert (
        session_client.post(PATH + "/login", json=session_account, headers=headers).status_code
        == 403
    )
    headers = challenge(session_client)
    session_client.cookies.clear()
    challenge(session_client)
    assert (
        session_client.post(PATH + "/login", json=session_account, headers=headers).status_code
        == 403
    )
    headers = challenge(session_client)
    headers.pop("Origin")
    headers["Referer"] = ORIGIN + "/docs?not-a-credential"
    assert (
        session_client.post(PATH + "/login", json=session_account, headers=headers).status_code
        == 200
    )


@pytest.mark.integration
def test_secure_cookie_attributes_and_lifetime(session_client, session_account, session_settings):
    config = session_settings.model_copy(
        update={"browser_cookie_secure": True, "browser_cookie_seconds": 120}
    )
    app.dependency_overrides[get_settings] = lambda: config
    session_client.base_url = "https://testserver"
    response = browser_login(session_client, session_account)
    for cookie in response.headers.get_list("set-cookie"):
        assert cookie.startswith("__Secure-") and "Secure" in cookie and "HttpOnly" in cookie
        assert "Domain=" not in cookie
    assert "Max-Age=120" in response.headers.get_list("set-cookie")[1]
    assert session_client.get(PATH + "/session").status_code == 200


@pytest.mark.integration
@pytest.mark.parametrize("status", ["pending", "suspended", "deactivated"])
def test_browser_account_restrictions(session_client, session_account, identity_engine, status):
    with Session(identity_engine) as session, session.begin():
        user = session.scalar(select(User).where(User.email == session_account["email"]))
        user.status = status
    response = session_client.post(
        PATH + "/login", json=session_account, headers=challenge(session_client)
    )
    assert response.status_code == 401 and "set-cookie" not in response.headers


@pytest.mark.integration
def test_fixation_replay_and_concurrent_refresh(session_client, session_account):
    first = browser_login(session_client, session_account)
    old = dict(session_client.cookies)
    second = browser_login(session_client, session_account)
    assert first.json()["session_id"] != second.json()["session_id"]
    assert dict(session_client.cookies) != old
    headers = challenge(session_client) | {"Content-Type": "application/json"}
    # Independent HTTP requests carry the same snapshot; shared cookie jars are not raced.
    raw_cookie = "; ".join(f"{k}={v}" for k, v in session_client.cookies.items())

    def refresh(_):
        with TestClient(app) as client:
            return client.post(PATH + "/refresh", json={}, headers=headers | {"Cookie": raw_cookie})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(refresh, range(2)))
    assert sorted(r.status_code for r in results) == [200, 401]
    winner = next(r for r in results if r.status_code == 200)
    session_client.cookies.clear()
    session_client.cookies.update(winner.cookies)
    assert session_client.get(PATH + "/session").status_code == 401
    assert (
        session_client.post(
            PATH + "/refresh", json={}, headers=challenge(session_client)
        ).status_code
        == 401
    )
    assert not dict(session_client.cookies)


@pytest.mark.integration
def test_logout_all_and_reset_revoke_browser_and_bearer(
    session_client, session_account, session_settings, identity_engine
):
    browser_login(session_client, session_account)
    original = dict(session_client.cookies)
    pair = session_client.post(
        "/api/v1/auth/login", json=session_account | {"session_mode": "refresh"}
    ).json()
    assert (
        session_client.post(
            PATH + "/logout-all", json={}, headers=challenge(session_client)
        ).status_code
        == 204
    )
    assert (
        session_client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer " + pair["access_token"]}
        ).status_code
        == 401
    )
    session_client.cookies.clear()
    for name, value in original.items():
        session_client.cookies.set(name, value, domain="testserver.local", path=PATH)
    assert session_client.get(PATH + "/session").status_code == 401
    browser_login(session_client, session_account)
    pair = session_client.post("/api/v1/auth/login", json=session_account).json()
    assert (
        session_client.post(
            "/api/v1/auth/forgot-password", json={"email": session_account["email"]}
        ).status_code
        == 202
    )
    with Session(identity_engine) as session:
        token = next(
            m["token"]
            for m in local_messages(
                session, session_account["email"], session_settings, confirmed=True
            )
            if m["purpose"] == "reset_password"
        )
    new_password = token_urlsafe(30)
    payload = {"token": token, "new_password": new_password}
    assert session_client.post("/api/v1/auth/reset-password", json=payload).status_code == 200
    assert session_client.post("/api/v1/auth/reset-password", json=payload).status_code == 400
    assert session_client.get(PATH + "/session").status_code == 401
    assert (
        session_client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer " + pair["access_token"]}
        ).status_code
        == 401
    )
    assert (
        session_client.post(
            PATH + "/refresh", json={}, headers=challenge(session_client)
        ).status_code
        == 401
    )
    browser_login(session_client, session_account | {"password": new_password})


@pytest.mark.integration
def test_expiry_and_revocation(session_client, session_account, identity_engine):
    response = browser_login(session_client, session_account)
    with Session(identity_engine) as session, session.begin():
        family = session.get(AuthSession, UUID(response.json()["session_id"]))
        family.created_at = datetime.now(UTC) - timedelta(days=2)
        family.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert session_client.get(PATH + "/session").status_code == 401
    assert (
        session_client.post(
            PATH + "/refresh", json={}, headers=challenge(session_client)
        ).status_code
        == 401
    )


@pytest.mark.integration
def test_expired_browser_access_can_refresh_and_no_bearer_fallback(
    session_client, session_account, session_settings
):
    browser_login(session_client, session_account)
    original = session_client.cookies.get("movie_access")
    claims = jwt.decode(original, options={"verify_signature": False})
    for key in ("iat", "nbf", "exp"):
        claims[key] -= 3600
    expired = jwt.encode(
        claims,
        session_settings.access_signing_key.get_secret_value(),
        algorithm="HS256",
        headers={"typ": "at+jwt"},
    )
    session_client.cookies.set("movie_access", expired, domain="testserver.local", path=PATH)
    assert session_client.get(PATH + "/session").status_code == 401
    assert (
        session_client.post(
            PATH + "/refresh", json={}, headers=challenge(session_client)
        ).status_code
        == 200
    )
    session_client.cookies.clear()
    assert (
        session_client.get(
            PATH + "/session", headers={"Authorization": "Bearer " + original}
        ).status_code
        == 401
    )


@pytest.mark.integration
def test_browser_invalid_password_and_csrf_signature(session_client, session_account):
    headers = challenge(session_client)
    response = session_client.post(
        PATH + "/login", json=session_account | {"password": token_urlsafe(30)}, headers=headers
    )
    assert response.status_code == 401 and "Invalid email or password" in response.text
    parts = headers["X-CSRF-Token"].split(".")
    parts[1] = parts[1][:-4] + "AAAA"
    headers["X-CSRF-Token"] = ".".join(parts)
    assert (
        session_client.post(PATH + "/login", json=session_account, headers=headers).status_code
        == 403
    )


@pytest.mark.integration
def test_browser_fail_closed_and_throttling(session_client, session_account, monkeypatch):
    from app.api import browser
    from app.services import rate_limits

    def broken(*args, **kwargs):
        raise SQLAlchemyError("private-error")

    monkeypatch.setattr(browser, "authenticate", broken)
    response = session_client.post(
        PATH + "/login", json=session_account, headers=challenge(session_client)
    )
    assert response.status_code == 503 and "private" not in response.text
    del app.dependency_overrides[limit_logout]
    monkeypatch.setattr(
        rate_limits,
        "get_registration_redis",
        lambda: (_ for _ in ()).throw(RuntimeError("private-error")),
    )
    assert (
        session_client.post(
            PATH + "/refresh", json={}, headers=challenge(session_client)
        ).status_code
        == 503
    )


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_all_unsafe_methods_require_csrf(method):
    request = Request({"type": "http", "method": method, "headers": []})
    with pytest.raises(HTTPException) as caught:
        validate_csrf(request, Settings(_env_file=None))
    assert caught.value.status_code == 403


def test_cors_host_and_security_headers():
    def unused_database():
        # Missing cookies are rejected before any query; this header unit test needs no service.
        yield None

    app.dependency_overrides[get_db_session] = unused_database
    with TestClient(app) as client:
        approved = client.options(
            PATH + "/login",
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "x-csrf-token,content-type",
            },
        )
        assert approved.status_code == 200
        assert approved.headers["access-control-allow-origin"] == ORIGIN
        assert approved.headers["access-control-allow-credentials"] == "true"
        denied = client.options(
            PATH + "/login",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
        )
        assert denied.status_code == 400 and "access-control-allow-origin" not in denied.headers
        assert client.get("/health", headers={"Host": "evil.example"}).status_code == 400
        assert (
            client.options(
                PATH + "/login",
                headers={
                    "Host": "evil.example",
                    "Origin": ORIGIN,
                    "Access-Control-Request-Method": "POST",
                },
            ).status_code
            == 400
        )
        response = client.get(PATH + "/session")
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "default-src 'none'" in response.headers["content-security-policy"]
        assert client.get("/docs").status_code == 200


@pytest.mark.parametrize(
    "update",
    [
        {"browser_origins": ["*"]},
        {"browser_origins": ["https://example.com/path"]},
        {"browser_origins": ["null"]},
        {"trusted_hosts": ["*"]},
        {"browser_origins": ["https://user:password@example.com"]},
    ],
)
def test_browser_config_rejects_unsafe_allowlists(update):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **update)


def test_production_requires_explicit_secure_config(monkeypatch):
    kwargs = dict(
        environment="production",
        database_url="postgresql://u:secret@db/movie",
        redis_url="redis://:secret@cache/0",
    )
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **kwargs)
    config = Settings(
        _env_file=None,
        **kwargs,
        browser_cookie_secure=True,
        browser_origins=["https://movies.example"],
        trusted_hosts=["movies.example"],
    )
    monkeypatch.setattr("app.core.browser_middleware.get_settings", lambda: config)
    with TestClient(app, base_url="https://movies.example") as client:
        assert client.get("/health").headers["strict-transport-security"] == "max-age=31536000"


def test_duplicate_cookie_rejected():
    config = Settings(_env_file=None)
    name = cookie_name("refresh", config)
    request = Request({"type": "http", "headers": [(b"cookie", f"{name}=a; {name}=b".encode())]})
    with pytest.raises(HTTPException):
        binding(request, config)
