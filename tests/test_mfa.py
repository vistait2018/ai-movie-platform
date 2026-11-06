import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import UUID, uuid4

import pyotp
import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException, Request
from pydantic import SecretStr
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_sessions import (
    headers,
    login,
    refresh,
)
from test_sessions import (
    session_account as session_account,
)
from test_sessions import (
    session_client as session_client,
)
from test_sessions import (
    session_settings as session_settings,
)

from app.admin_bootstrap import bootstrap
from app.core.passwords import hash_password
from app.core.settings import get_settings
from app.main import app
from app.models.identity import (
    AuthSession,
    MFAAssurance,
    MFAFactor,
    MFARecoveryCode,
    Role,
    SecurityEvent,
    User,
    UserRole,
)
from app.services import authorization as policy
from app.services import mfa, rate_limits
from app.services.sessions import start_session

pytestmark = pytest.mark.integration
BASE = "/api/v1/auth/mfa"


@pytest.fixture(autouse=True)
def isolated_mfa_limits(monkeypatch):
    monkeypatch.setattr("app.api.mfa.check_action_limits", lambda *args, **kwargs: None)


def enrollment(client, account, pair):
    response = client.post(
        BASE + "/enroll", headers=headers(pair), json={"password": account["password"]}
    )
    assert response.status_code == 200, response.text
    return response.json()["secret"]


def proof(client, account, pair, code, action="verify"):
    return client.post(
        BASE + "/" + action,
        headers=headers(pair),
        json={"password": account["password"], "code": code},
    )


@pytest.fixture
def enrolled(session_client, session_account):
    pair = login(session_client, session_account)
    secret = enrollment(session_client, session_account, pair)
    response = proof(session_client, session_account, pair, pyotp.TOTP(secret).now(), "confirm")
    assert response.status_code == 200, response.text
    return pair, secret, response.json()["recovery_codes"]


def user_id(client, pair):
    return UUID(client.get("/api/v1/auth/me", headers=headers(pair)).json()["id"])


def role(engine, uid, code="super_admin"):
    with Session(engine) as session, session.begin():
        selected = session.scalar(select(Role).where(Role.code == code))
        session.add(UserRole(user_id=uid, role_id=selected.id))


def catalogue(client, pair):
    return client.get("/api/v1/authorization/roles", headers=headers(pair))


def test_enrollment_ciphertext_hashes_and_redaction(
    session_client, session_account, identity_engine, session_settings, caplog
):
    with caplog.at_level(logging.INFO):
        pair = login(session_client, session_account)
        secret = enrollment(session_client, session_account, pair)
        response = proof(session_client, session_account, pair, pyotp.TOTP(secret).now(), "confirm")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    codes = response.json()["recovery_codes"]
    assert len(codes) == len(set(codes)) == 8
    uid = user_id(session_client, pair)
    with Session(identity_engine) as session:
        factor = session.get(MFAFactor, uid)
        assert secret.encode() not in factor.encrypted_secret
        assert mfa.secret_for(factor, session_settings) == secret
        digests = session.scalars(
            select(MFARecoveryCode.digest).where(MFARecoveryCode.user_id == uid)
        ).all()
        assert len(digests) == 8 and all(value not in digests for value in codes)
        assert {mfa.recovery_digest(uid, value) for value in codes} == set(digests)
    assert secret not in caplog.text and all(value not in caplog.text for value in codes)
    assert (
        session_account["password"] not in caplog.text and pair["access_token"] not in caplog.text
    )
    assert (
        proof(
            session_client, session_account, pair, pyotp.TOTP(secret).now(), "confirm"
        ).status_code
        == 403
    )
    assert (
        session_client.post(
            BASE + "/enroll", json={"password": session_account["password"]}, headers=headers(pair)
        ).status_code
        == 409
    )


@pytest.mark.parametrize("kind", ["legacy", "password", "missing_key", "invalid_key"])
def test_enrollment_fails_closed(session_client, session_account, session_settings, kind):
    pair = login(session_client, session_account, legacy=kind == "legacy")
    password = "wrong-password" if kind == "password" else session_account["password"]
    if kind in {"missing_key", "invalid_key"}:
        app.dependency_overrides[get_settings] = lambda: session_settings.model_copy(
            update={"mfa_encryption_key": None if kind == "missing_key" else SecretStr("invalid")}
        )
    response = session_client.post(
        BASE + "/enroll", json={"password": password}, headers=headers(pair)
    )
    assert response.status_code == (503 if kind.endswith("key") else 403)
    assert password not in response.text


@pytest.mark.parametrize("kind", ["other_session", "expired", "wrong_code", "wrong_password"])
def test_confirmation_bound_pending_and_reauthenticated(
    session_client, session_account, identity_engine, kind
):
    pair = login(session_client, session_account)
    secret = enrollment(session_client, session_account, pair)
    uid = user_id(session_client, pair)
    code = pyotp.TOTP(secret).now()
    if kind == "other_session":
        pair = login(session_client, session_account)
    if kind == "expired":
        with Session(identity_engine) as session, session.begin():
            session.get(MFAFactor, uid).enrollment_expires_at = datetime.now(UTC) - timedelta(
                seconds=1
            )
    if kind == "wrong_code":
        code = "abcdef"
    account = session_account | ({"password": "wrong"} if kind == "wrong_password" else {})
    assert proof(session_client, account, pair, code, "confirm").status_code == 403
    with Session(identity_engine) as session:
        assert session.get(MFAFactor, uid).confirmed_at is None
        assert session.get(MFAAssurance, UUID(pair["session_id"])) is None


def test_replay_and_future_window_counter(
    session_client, session_account, enrolled, identity_engine
):
    pair, secret, _ = enrolled
    with Session(identity_engine) as session:
        accepted = session.get(MFAFactor, user_id(session_client, pair)).last_counter
    assert (
        proof(
            session_client, session_account, pair, pyotp.TOTP(secret).at(accepted * 30)
        ).status_code
        == 403
    )
    future = pyotp.TOTP(secret).at(datetime.now(UTC) + timedelta(seconds=30))
    assert proof(session_client, session_account, pair, future).status_code == 204
    assert proof(session_client, session_account, pair, future).status_code == 403
    assert proof(session_client, session_account, pair, pyotp.TOTP(secret).now()).status_code == 403


@pytest.mark.parametrize("recovery", [False, True])
def test_concurrent_proof_single_use(session_client, session_account, enrolled, recovery):
    pair, secret, codes = enrolled
    code = (
        codes[0] if recovery else pyotp.TOTP(secret).at(datetime.now(UTC) + timedelta(seconds=30))
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: proof(session_client, session_account, pair, code).status_code, range(2)
            )
        )
    assert sorted(results) == [204, 403]


def test_session_bound_expiry_and_refresh_does_not_extend(
    session_client, session_account, enrolled, identity_engine
):
    pair, _, _ = enrolled
    uid = user_id(session_client, pair)
    role(identity_engine, uid)
    assert catalogue(session_client, pair).status_code == 200
    other = login(session_client, session_account)
    assert catalogue(session_client, other).status_code == 403
    with Session(identity_engine) as session:
        expiry = session.get(MFAAssurance, UUID(pair["session_id"])).expires_at
    rotated = refresh(session_client, pair)
    assert rotated.status_code == 200
    assert catalogue(session_client, rotated.json()).status_code == 200
    assert catalogue(session_client, pair).status_code == 401
    with Session(identity_engine) as session, session.begin():
        assurance = session.get(MFAAssurance, UUID(pair["session_id"]))
        assert assurance.expires_at == expiry
        assurance.verified_at = datetime.now(UTC) - timedelta(minutes=10)
        assurance.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert catalogue(session_client, rotated.json()).status_code == 403


def test_recovery_cannot_replay_and_does_not_reissue_codes(
    session_client, session_account, enrolled
):
    pair, _, codes = enrolled
    other = login(session_client, session_account)
    assert proof(session_client, session_account, other, codes[0]).status_code == 204
    assert proof(session_client, session_account, pair, codes[0]).status_code == 403
    assert proof(session_client, session_account, pair, "invalid-recovery").status_code == 403


@pytest.mark.parametrize("operation", ["logout", "logout-all", "password_reset", "role_changed"])
def test_assurance_invalidated_by_revocation(
    session_client, session_account, enrolled, identity_engine, operation
):
    from app.services.sessions import revoke_user_sessions

    pair, _, _ = enrolled
    uid = user_id(session_client, pair)
    role(identity_engine, uid)
    if operation.startswith("logout"):
        assert (
            session_client.post("/api/v1/auth/" + operation, headers=headers(pair)).status_code
            == 204
        )
    else:
        with Session(identity_engine) as session, session.begin():
            session.scalar(select(User).where(User.id == uid).with_for_update())
            revoke_user_sessions(session, uid, datetime.now(UTC), operation)
    assert catalogue(session_client, pair).status_code == 401
    with Session(identity_engine) as session:
        with pytest.raises(HTTPException):
            mfa.require_assurance(session, session.get(User, uid), UUID(pair["session_id"]))


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_environment_gate_even_with_real_assurance(
    session_client, session_account, enrolled, identity_engine, session_settings, environment
):
    pair, _, _ = enrolled
    role(identity_engine, user_id(session_client, pair))
    assert catalogue(session_client, pair).status_code == 200
    app.dependency_overrides[get_settings] = lambda: session_settings.model_copy(
        update={"environment": environment}
    )
    assert catalogue(session_client, pair).status_code == 403


def test_missing_assurance_and_forged_claims_cannot_administer(
    session_client, session_account, identity_engine
):
    import jwt

    pair = login(session_client, session_account)
    uid = user_id(session_client, pair)
    role(identity_engine, uid)
    assert catalogue(session_client, pair).status_code == 403
    assert (
        session_client.put(
            f"/api/v1/users/{uuid4()}/roles/creator", headers=headers(pair)
        ).status_code
        == 403
    )
    legacy = login(session_client, session_account, legacy=True)
    assert catalogue(session_client, legacy).status_code == 403
    assert (
        session_client.post(
            BASE + "/verify",
            json={"password": session_account["password"], "code": "123456", "mfa_verified": True},
            headers=headers(pair),
        ).status_code
        == 422
    )
    assert "mfa" not in jwt.decode(pair["access_token"], options={"verify_signature": False})


def test_self_disable_revokes_sessions_and_factor(
    session_client, session_account, enrolled, identity_engine
):
    pair, _, codes = enrolled
    uid = user_id(session_client, pair)
    assert proof(session_client, session_account, pair, codes[0], "disable").status_code == 204
    assert session_client.get("/api/v1/auth/me", headers=headers(pair)).status_code == 401
    with Session(identity_engine) as session:
        assert session.get(MFAFactor, uid) is None
        assert session.get(MFAAssurance, UUID(pair["session_id"])) is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(MFARecoveryCode)
                .where(MFARecoveryCode.user_id == uid)
            )
            == 0
        )


def test_privileged_disable_requires_role_retirement(
    session_client, session_account, enrolled, identity_engine
):
    pair, _, codes = enrolled
    role(identity_engine, user_id(session_client, pair))
    assert proof(session_client, session_account, pair, codes[0], "disable").status_code == 409
    assert catalogue(session_client, pair).status_code == 200


def test_proof_transaction_rollback(session_client, session_account, enrolled, identity_engine):
    pair, _, codes = enrolled
    uid = user_id(session_client, pair)

    def reject(session):
        raise SQLAlchemyError("private-db-data")

    event.listen(Session, "before_commit", reject)
    try:
        response = proof(session_client, session_account, pair, codes[0])
        assert response.status_code == 503 and "private" not in response.text
    finally:
        event.remove(Session, "before_commit", reject)
    with Session(identity_engine) as session:
        assert (
            session.get(MFARecoveryCode, (uid, mfa.recovery_digest(uid, codes[0]))).consumed_at
            is None
        )
    assert proof(session_client, session_account, pair, codes[0]).status_code == 204


def test_browser_enrollment_csrf_and_transport_isolation(session_client, session_account):
    base = "/api/v1/auth/browser"

    def csrf():
        response = session_client.get(base + "/csrf")
        return {"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": response.json()["csrf_token"]}

    assert (
        session_client.post(base + "/login", json=session_account, headers=csrf()).status_code
        == 200
    )
    data = {"password": session_account["password"]}
    assert session_client.post(base + "/mfa/enroll", json=data).status_code == 403
    response = session_client.post(base + "/mfa/enroll", json=data, headers=csrf())
    assert response.status_code == 200
    data["code"] = pyotp.TOTP(response.json()["secret"]).now()
    assert session_client.post(base + "/mfa/confirm", json=data, headers=csrf()).status_code == 200
    assert session_client.post(BASE + "/verify", json=data).status_code == 401


def test_real_redis_mfa_shared_scope_account_limit(session_settings, monkeypatch):
    from hashlib import sha256

    from redis import Redis

    redis = Redis.from_url(session_settings.redis_url.get_secret_value())
    monkeypatch.setattr(rate_limits, "get_registration_redis", lambda: redis)
    identity = "mfa013-" + uuid4().hex
    addresses = ["ip-" + uuid4().hex for _ in range(2)]
    keys = [
        "auth:action:"
        + sha256(b"mfa_mutations").hexdigest()
        + ":"
        + kind
        + ":"
        + sha256(value.encode()).hexdigest()
        for kind, value in [("identity", identity)] + [("ip", address) for address in addresses]
    ]
    try:
        for index, address in enumerate(addresses):
            request = Request(
                {
                    "type": "http",
                    "path": BASE + ("/verify" if index else "/confirm"),
                    "headers": [],
                    "client": (address, 1),
                }
            )
            if index:
                with pytest.raises(HTTPException) as denied:
                    rate_limits.check_action_limits(
                        request, identity, session_settings, 1, scope_name="mfa_mutations"
                    )
                assert denied.value.status_code == 429
            else:
                rate_limits.check_action_limits(
                    request, identity, session_settings, 1, scope_name="mfa_mutations"
                )
        assert 0 < redis.ttl(keys[0]) <= session_settings.mfa_window_seconds
    finally:
        redis.delete(*keys)
        redis.close()


def test_administrator_provisioning_reset_and_revocation(
    session_client, session_account, enrolled, identity_engine, session_settings
):
    from app.dev_verify import verify_local_user

    admin, _, _ = enrolled
    role(identity_engine, user_id(session_client, admin))
    account = {
        "email": uuid4().hex + "@example.com",
        "password": token_urlsafe(30),
        "display_name": "Recipient",
    }
    assert session_client.post("/api/v1/auth/register", json=account).status_code == 202
    with Session(identity_engine) as session:
        verify_local_user(session, account["email"], session_settings, confirmed=True)
    recipient = login(session_client, {"email": account["email"], "password": account["password"]})
    uid = user_id(session_client, recipient)
    resource = f"/api/v1/users/{uid}/roles/"
    reset = f"/api/v1/auth/users/{uid}/mfa/reset"
    assert session_client.put(resource + "super_admin", headers=headers(admin)).status_code == 409
    secret = enrollment(session_client, account, recipient)
    codes = proof(session_client, account, recipient, pyotp.TOTP(secret).now(), "confirm").json()[
        "recovery_codes"
    ]
    assert session_client.post(reset, headers=headers(recipient)).status_code == 403
    assert session_client.put(resource + "super_admin", headers=headers(admin)).status_code == 204
    assert catalogue(session_client, recipient).status_code == 401
    recipient = login(session_client, {"email": account["email"], "password": account["password"]})
    assert catalogue(session_client, recipient).status_code == 403
    assert proof(session_client, account, recipient, codes[0]).status_code == 204
    assert catalogue(session_client, recipient).status_code == 200
    assert session_client.post(reset, headers=headers(admin)).status_code == 409
    assert (
        session_client.delete(resource + "super_admin", headers=headers(admin)).status_code == 204
    )
    assert catalogue(session_client, recipient).status_code == 401
    assert session_client.post(reset, headers=headers(admin)).status_code == 204
    with Session(identity_engine) as session:
        assert session.get(MFAFactor, uid) is None
        assert (
            session.scalar(
                select(SecurityEvent.id).where(
                    SecurityEvent.subject_user_id == uid, SecurityEvent.event.like("mfa_reset:%")
                )
            )
            is not None
        )


def test_confirmation_rollback_never_confirms_or_issues_codes(
    session_client, session_account, identity_engine
):
    pair = login(session_client, session_account)
    secret = enrollment(session_client, session_account, pair)
    uid = user_id(session_client, pair)

    def reject(session):
        raise SQLAlchemyError("private-detail")

    event.listen(Session, "before_commit", reject)
    try:
        assert (
            proof(
                session_client, session_account, pair, pyotp.TOTP(secret).now(), "confirm"
            ).status_code
            == 503
        )
    finally:
        event.remove(Session, "before_commit", reject)
    with Session(identity_engine) as session:
        assert session.get(MFAFactor, uid).confirmed_at is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(MFARecoveryCode)
                .where(MFARecoveryCode.user_id == uid)
            )
            == 0
        )


def test_tampered_encrypted_secret_fails_sanitized(
    session_client, session_account, enrolled, identity_engine
):
    pair, secret, _ = enrolled
    uid = user_id(session_client, pair)
    with Session(identity_engine) as session, session.begin():
        session.get(MFAFactor, uid).encrypted_secret = b"corrupt-ciphertext"
    response = proof(session_client, session_account, pair, pyotp.TOTP(secret).now())
    assert response.status_code == 503
    assert secret not in response.text and "ciphertext" not in response.text


def test_enrollment_rechecks_revocation_after_authentication(
    session_client, session_account, identity_engine, monkeypatch
):
    from app.api import mfa as adapter
    from app.services.sessions import revoke_user_sessions

    pair = login(session_client, session_account)
    uid = user_id(session_client, pair)
    original = adapter.lock_and_reauthenticate

    def revoke_before_lock(session, principal, target_id, settings, **kwargs):
        with Session(identity_engine) as other, other.begin():
            other.scalar(select(User).where(User.id == uid).with_for_update())
            revoke_user_sessions(other, uid, datetime.now(UTC), "logout_all")
        return original(session, principal, target_id, settings, **kwargs)

    monkeypatch.setattr(adapter, "lock_and_reauthenticate", revoke_before_lock)
    response = session_client.post(
        BASE + "/enroll", json={"password": session_account["password"]}, headers=headers(pair)
    )
    assert response.status_code == 401
    with Session(identity_engine) as session:
        assert session.get(MFAFactor, uid) is None


@pytest.fixture
def bootstrap_accounts(migration_engine, session_settings):
    config = Config("alembic.ini")
    with migration_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    instant = datetime.now(UTC)
    accounts = []
    for _ in range(2):
        uid, password = uuid4(), token_urlsafe(32)
        with Session(migration_engine) as session, session.begin():
            session.add(
                User(
                    id=uid,
                    email=uuid4().hex + "@example.com",
                    display_name="Bootstrap fixture",
                    password_hash=hash_password(password),
                    status="active",
                    email_verified_at=instant,
                )
            )
        with Session(migration_engine) as session:
            with session.begin():
                user = session.get(User, uid)
                pair = start_session(session, user, session_settings, instant)
            issued = mfa.enroll(
                session, user, session.get(AuthSession, pair.session_id), password, session_settings
            )
            mfa.confirm(
                session,
                user,
                session.get(AuthSession, pair.session_id),
                password,
                pyotp.TOTP(issued.secret).now(),
                session_settings,
            )
        accounts.append((uid, password, issued.secret, pair))
    return migration_engine, accounts


@pytest.mark.parametrize("unavailable", [False, True])
def test_mfa_adapter_enforces_real_limiter(
    session_client, session_account, session_settings, monkeypatch, unavailable
):
    from hashlib import sha256

    from fastapi.testclient import TestClient
    from redis import Redis
    from redis.exceptions import RedisError

    pair = login(session_client, session_account)
    uid = user_id(session_client, pair)
    redis = Redis.from_url(session_settings.redis_url.get_secret_value())
    address = "mfa-adapter-" + uuid4().hex
    monkeypatch.setattr("app.api.mfa.check_action_limits", rate_limits.check_action_limits)

    def failed():
        raise RedisError("private-redis-detail")

    monkeypatch.setattr(
        rate_limits, "get_registration_redis", failed if unavailable else lambda: redis
    )
    app.dependency_overrides[get_settings] = lambda: session_settings.model_copy(
        update={"mfa_requests_per_window": 1}
    )
    scope = sha256(b"mfa_mutations").hexdigest()
    keys = [
        "auth:action:" + scope + ":" + kind + ":" + sha256(value.encode()).hexdigest()
        for kind, value in (("ip", address), ("identity", str(uid)))
    ]
    try:
        with TestClient(app, client=(address, 1)) as client:
            response = client.post(
                BASE + "/enroll",
                json={"password": session_account["password"]},
                headers=headers(pair),
            )
            assert response.status_code == (503 if unavailable else 200)
            if not unavailable:
                assert proof(client, session_account, pair, "123456", "confirm").status_code == 429
            assert "private-redis" not in response.text
    finally:
        redis.delete(*keys)
        redis.close()


@pytest.mark.parametrize(
    "kind", ["unconfirmed", "staging", "production", "wrong_password", "replay"]
)
def test_bootstrap_restrictions(bootstrap_accounts, session_settings, kind):
    engine, accounts = bootstrap_accounts
    uid, password, secret, _ = accounts[0]
    settings = (
        session_settings.model_copy(update={"environment": kind})
        if kind in {"staging", "production"}
        else session_settings
    )
    with Session(engine) as session:
        accepted_counter = session.get(MFAFactor, uid).last_counter
    code = (
        pyotp.TOTP(secret).at(accepted_counter * 30)
        if kind == "replay"
        else pyotp.TOTP(secret).at(datetime.now(UTC) + timedelta(seconds=30))
    )
    with Session(engine) as session, pytest.raises((ValueError, HTTPException)):
        bootstrap(
            session,
            uid,
            "incorrect" if kind == "wrong_password" else password,
            code,
            settings,
            confirmed=kind != "unconfirmed",
        )
    with Session(engine) as session:
        assert "super_admin" not in policy.roles_for(session, uid)


def test_bootstrap_concurrency_one_admin_and_audit(bootstrap_accounts, session_settings):
    engine, accounts = bootstrap_accounts

    def provision(account):
        uid, password, secret, _ = account
        try:
            with Session(engine) as session:
                bootstrap(
                    session,
                    uid,
                    password,
                    pyotp.TOTP(secret).at(datetime.now(UTC) + timedelta(seconds=30)),
                    session_settings,
                    confirmed=True,
                )
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(provision, accounts)) == [False, True]
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(SecurityEvent)
                .where(SecurityEvent.event == "initial_admin_provisioned")
            )
            == 1
        )
        for uid, _, _, pair in accounts:
            if "super_admin" in policy.roles_for(session, uid):
                assert session.get(AuthSession, pair.session_id).revoked_at is not None


@pytest.mark.parametrize("existing", ["inactive", "permanent_marker"])
def test_bootstrap_cannot_be_reused(bootstrap_accounts, session_settings, existing):
    engine, accounts = bootstrap_accounts
    uid, password, secret, _ = accounts[0]
    other = accounts[1][0]
    with Session(engine) as session, session.begin():
        if existing == "inactive":
            administrator = session.scalar(select(Role).where(Role.code == "super_admin"))
            session.add(UserRole(user_id=other, role_id=administrator.id))
            session.get(User, other).status = "suspended"
        else:
            session.add(SecurityEvent(subject_user_id=other, event="initial_admin_provisioned"))
    with Session(engine) as session, pytest.raises(ValueError):
        bootstrap(
            session,
            uid,
            password,
            pyotp.TOTP(secret).at(datetime.now(UTC) + timedelta(seconds=30)),
            session_settings,
            confirmed=True,
        )


def test_bootstrap_rollback_preserves_role_and_sessions(bootstrap_accounts, session_settings):
    engine, accounts = bootstrap_accounts
    uid, password, secret, pair = accounts[0]

    def reject(session):
        raise SQLAlchemyError("private-rollback")

    event.listen(Session, "before_commit", reject)
    try:
        with Session(engine) as session, pytest.raises(SQLAlchemyError):
            bootstrap(
                session,
                uid,
                password,
                pyotp.TOTP(secret).at(datetime.now(UTC) + timedelta(seconds=30)),
                session_settings,
                confirmed=True,
            )
    finally:
        event.remove(Session, "before_commit", reject)
    with Session(engine) as session:
        assert "super_admin" not in policy.roles_for(session, uid)
        assert session.get(AuthSession, pair.session_id).revoked_at is None


def test_downgrade_refuses_enrolled_credentials(bootstrap_accounts):
    engine, accounts = bootstrap_accounts
    config = Config("alembic.ini")
    with pytest.raises(RuntimeError, match="Populated MFA tables"):
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0005_refresh_sessions")
    with Session(engine) as session:
        assert session.get(MFAFactor, accounts[0][0]).confirmed_at is not None


def test_session_cleanup_preserves_confirmed_factor(
    session_client, session_account, enrolled, identity_engine
):
    pair, _, codes = enrolled
    uid = user_id(session_client, pair)
    other = login(session_client, session_account)
    with Session(identity_engine) as session, session.begin():
        session.delete(session.get(AuthSession, UUID(pair["session_id"])))
    with Session(identity_engine) as session:
        factor = session.get(MFAFactor, uid)
        assert factor.confirmed_at is not None and factor.enrollment_session_id is None
    assert proof(session_client, session_account, other, codes[0]).status_code == 204
