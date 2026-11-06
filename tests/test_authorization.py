import logging
from concurrent.futures import ThreadPoolExecutor
from secrets import token_urlsafe
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_sessions import session_client as session_client
from test_sessions import session_settings as session_settings

from app.core.settings import get_settings
from app.dev_verify import verify_local_user
from app.main import app
from app.models.identity import (
    AccessGrant,
    AuthSession,
    Permission,
    Role,
    RolePermission,
    SecurityEvent,
    User,
    UserRole,
)
from app.services import authorization as policy
from app.services.rate_limits import limit_authorization

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def isolated_authorization_limits(isolated_settings):
    app.dependency_overrides[limit_authorization] = lambda: None


@pytest.fixture
def identities(session_client, session_settings, identity_engine):
    result = []
    for index in range(3):
        data = {
            "email": uuid4().hex + "@example.com",
            "password": token_urlsafe(30),
            "display_name": "RBAC fixture " + str(index),
        }
        assert session_client.post("/api/v1/auth/register", json=data).status_code == 202
        with Session(identity_engine) as session:
            verify_local_user(session, data["email"], session_settings, confirmed=True)
            user = session.scalar(select(User).where(User.email == data["email"]))
            data["id"] = str(user.id)
        result.append(data)
    return result


def auth(client, account, *, refresh=False):
    data = {"email": account["email"], "password": account["password"]}
    if refresh:
        data["session_mode"] = "refresh"
    response = client.post("/api/v1/auth/login", json=data)
    assert response.status_code == 200
    return response.json()


def headers(pair):
    return {"Authorization": "Bearer " + pair["access_token"]}


def add_role(engine, account, code):
    # Explicit test-only provisioning in a disposable database, never production bootstrap.
    with Session(engine) as session, session.begin():
        role = session.scalar(select(Role).where(Role.code == code))
        session.add(UserRole(user_id=UUID(account["id"]), role_id=role.id))


def path(account):
    return "/api/v1/users/" + account["id"]


def test_owner_profile_read_update_and_mass_assignment(session_client, identities):
    owner = identities[0]
    pair = auth(session_client, owner)
    response = session_client.get(path(owner), headers=headers(pair))
    assert response.status_code == 200 and response.json()["email"] == owner["email"]
    assert response.headers["cache-control"] == "no-store"
    response = session_client.patch(
        path(owner), json={"display_name": "Updated viewer"}, headers=headers(pair)
    )
    assert response.status_code == 200 and response.json()["display_name"] == "Updated viewer"
    for forbidden in (
        {"roles": ["super_admin"]},
        {"status": "active"},
        {"email": "other@example.com"},
        {"permissions": ["roles:assign"]},
    ):
        response = session_client.patch(
            path(owner), json={"display_name": "Unsafe"} | forbidden, headers=headers(pair)
        )
        assert response.status_code == 422
    assert session_client.get(path(owner) + "/roles", headers=headers(pair)).json() == {
        "roles": ["viewer"]
    }


@pytest.mark.parametrize("operation", ["get", "patch", "roles", "grant", "revoke"])
@pytest.mark.parametrize("exists", [True, False])
def test_cross_user_idor_is_uniformly_denied(session_client, identities, operation, exists):
    actor, target, _ = identities
    pair = auth(session_client, actor)
    resource = path(target) if exists else "/api/v1/users/" + str(uuid4())
    if operation == "get":
        response = session_client.get(resource, headers=headers(pair))
    elif operation == "patch":
        response = session_client.patch(
            resource, json={"display_name": "IDOR"}, headers=headers(pair)
        )
    elif operation == "roles":
        response = session_client.get(resource + "/roles", headers=headers(pair))
    elif operation == "grant":
        response = session_client.put(resource + "/roles/super_admin", headers=headers(pair))
    else:
        response = session_client.delete(resource + "/roles/viewer", headers=headers(pair))
    assert response.status_code == 403 and response.json() == {"detail": "Access denied"}


@pytest.mark.parametrize("code", ["creator", "moderator", "finance_admin", "admin"])
def test_non_admin_roles_cannot_assign_or_read_others(
    session_client, identities, identity_engine, code
):
    actor, target, _ = identities
    add_role(identity_engine, actor, code)
    pair = auth(session_client, actor)
    assert session_client.get(path(target), headers=headers(pair)).status_code == 403
    assert (
        session_client.get("/api/v1/authorization/roles", headers=headers(pair)).status_code == 403
    )
    assert (
        session_client.put(path(target) + "/roles/super_admin", headers=headers(pair)).status_code
        == 403
    )


def test_super_admin_assignment_revocation_and_current_grants(
    session_client, identities, identity_engine, caplog
):
    actor, target, _ = identities
    add_role(identity_engine, actor, "super_admin")
    administrator = auth(session_client, actor)
    recipient = auth(session_client, target, refresh=True)
    with caplog.at_level(logging.INFO, logger="movie.authorization"):
        response = session_client.put(
            path(target) + "/roles/creator", headers=headers(administrator)
        )
    assert response.status_code == 204
    assert session_client.get("/api/v1/auth/me", headers=headers(recipient)).status_code == 401
    assert (
        session_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": recipient["refresh_token"]}
        ).status_code
        == 401
    )
    new = auth(session_client, target)
    assert session_client.get(path(target) + "/roles", headers=headers(new)).json() == {
        "roles": ["creator", "viewer"]
    }
    # Idempotent grant does not revoke fresh credentials a second time.
    assert (
        session_client.put(
            path(target) + "/roles/creator", headers=headers(administrator)
        ).status_code
        == 204
    )
    assert session_client.get(path(target), headers=headers(new)).status_code == 200
    assert (
        session_client.delete(
            path(target) + "/roles/creator", headers=headers(administrator)
        ).status_code
        == 204
    )
    assert session_client.get(path(target), headers=headers(new)).status_code == 401
    latest = auth(session_client, target)
    assert session_client.get(path(target) + "/roles", headers=headers(latest)).json() == {
        "roles": ["viewer"]
    }
    assert session_client.get(path(target), headers=headers(administrator)).status_code == 200
    assert (
        session_client.patch(
            path(target),
            json={"display_name": "Admin-reviewed name"},
            headers=headers(administrator),
        ).status_code
        == 200
    )
    with Session(identity_engine) as session:
        records = session.scalars(
            select(SecurityEvent.event).where(SecurityEvent.subject_user_id == UUID(target["id"]))
        ).all()
        assert f"role_granted:{actor['id']}:creator" in records
        assert f"role_revoked:{actor['id']}:creator" in records
    assert target["password"] not in caplog.text
    assert recipient["refresh_token"] not in caplog.text
    assert administrator["access_token"] not in caplog.text


@pytest.mark.parametrize("code", ["viewer", "creator", "super_admin", "admin", "unknown"])
def test_no_self_role_mutation(session_client, identities, identity_engine, code):
    actor = identities[0]
    add_role(identity_engine, actor, "super_admin")
    pair = auth(session_client, actor)
    assert (
        session_client.put(path(actor) + "/roles/" + code, headers=headers(pair)).status_code == 403
    )
    assert (
        session_client.delete(path(actor) + "/roles/" + code, headers=headers(pair)).status_code
        == 403
    )


@pytest.mark.parametrize("status", ["pending", "suspended", "deactivated"])
def test_disabled_target_cannot_receive_roles(session_client, identities, identity_engine, status):
    actor, target, _ = identities
    add_role(identity_engine, actor, "super_admin")
    pair = auth(session_client, actor)
    with Session(identity_engine) as session, session.begin():
        session.get(User, UUID(target["id"])).status = status
    assert (
        session_client.put(path(target) + "/roles/creator", headers=headers(pair)).status_code
        == 403
    )


def test_last_eligible_super_admin_guard(session_client, identities, identity_engine):
    actor, target, _ = identities
    add_role(identity_engine, actor, "creator")
    add_role(identity_engine, target, "super_admin")
    # Explicitly delegated roles:assign in this isolated test; no implicit role hierarchy.
    with Session(identity_engine) as session, session.begin():
        role = session.scalar(select(Role).where(Role.code == "creator"))
        permission = session.scalar(select(Permission).where(Permission.code == "roles:assign"))
        link = RolePermission(role_id=role.id, permission_id=permission.id)
        session.add(link)
        ids = role.id, permission.id
        # Earlier cases retain fixture accounts in this disposable test database.
        # Temporarily deactivate only those other test administrators and restore them below.
        others = session.scalars(
            select(User)
            .join(UserRole)
            .join(Role)
            .where(Role.code == "super_admin", User.id != UUID(target["id"]))
        ).all()
        previous = [(user.id, user.status) for user in others]
        for user in others:
            user.status = "deactivated"
    try:
        pair = auth(session_client, actor)
        assert (
            session_client.delete(
                path(target) + "/roles/super_admin", headers=headers(pair)
            ).status_code
            == 409
        )
    finally:
        with Session(identity_engine) as session, session.begin():
            session.delete(session.get(RolePermission, ids))
            for user_id, status in previous:
                session.get(User, user_id).status = status


def test_unknown_roles_and_default_deny_even_for_super_admin(
    session_client, identities, identity_engine
):
    actor, target, _ = identities
    add_role(identity_engine, actor, "super_admin")
    pair = auth(session_client, actor)
    for code in ("admin", "visitor", "unknown"):
        assert (
            session_client.put(path(target) + "/roles/" + code, headers=headers(pair)).status_code
            == 403
        )
    assert session_client.get("/api/v1/authorization/roles", headers=headers(pair)).json() == {
        "roles": sorted(policy.ROLES)
    }
    with Session(identity_engine) as session:
        user = session.get(User, UUID(actor["id"]))
        with pytest.raises(HTTPException) as denied:
            policy.require_permission(session, user, "invented:permission")
        assert denied.value.status_code == 403
        with pytest.raises(HTTPException):
            policy.require_role(session, user, "admin")
        policy.require_role(session, user, "super_admin")


@pytest.mark.parametrize("status", ["suspended", "deactivated"])
def test_actor_disabled_or_revoked_fails_authentication(
    session_client, identities, identity_engine, status
):
    actor, target, _ = identities
    add_role(identity_engine, actor, "super_admin")
    pair = auth(session_client, actor)
    with Session(identity_engine) as session, session.begin():
        session.get(User, UUID(actor["id"])).status = status
    assert session_client.get(path(actor), headers=headers(pair)).status_code == 401
    assert (
        session_client.put(path(target) + "/roles/creator", headers=headers(pair)).status_code
        == 401
    )


def test_role_changes_roll_back_with_grants_and_audit(session_client, identities, identity_engine):
    actor, target, _ = identities
    add_role(identity_engine, actor, "super_admin")
    admin = auth(session_client, actor)
    pair = auth(session_client, target, refresh=True)

    def reject(session):
        raise SQLAlchemyError("private-database-detail")

    event.listen(Session, "before_commit", reject)
    try:
        response = session_client.put(path(target) + "/roles/creator", headers=headers(admin))
        assert response.status_code == 503 and "private" not in response.text
    finally:
        event.remove(Session, "before_commit", reject)
    assert session_client.get("/api/v1/auth/me", headers=headers(pair)).status_code == 200
    with Session(identity_engine) as session:
        assert policy.roles_for(session, UUID(target["id"])) == ["viewer"]
        assert session.get(AuthSession, UUID(pair["session_id"])).revoked_at is None


def test_no_permissions_blocks_profile_but_preserves_session_recovery(
    session_client, identities, identity_engine
):
    actor = identities[0]
    pair = auth(session_client, actor)
    with Session(identity_engine) as session, session.begin():
        links = session.scalars(select(UserRole).where(UserRole.user_id == UUID(actor["id"]))).all()
        for link in links:
            session.delete(link)
    assert session_client.get("/api/v1/auth/me", headers=headers(pair)).status_code == 403
    assert session_client.get(path(actor), headers=headers(pair)).status_code == 403
    assert session_client.post("/api/v1/auth/logout", headers=headers(pair)).status_code == 204


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_privileged_operations_fail_closed_without_mfa(
    session_client, identities, identity_engine, session_settings, environment
):
    actor, target, _ = identities
    add_role(identity_engine, actor, "super_admin")
    pair = auth(session_client, actor)
    app.dependency_overrides[get_settings] = lambda: session_settings.model_copy(
        update={"environment": environment}
    )
    assert session_client.get(path(actor), headers=headers(pair)).status_code == 200
    assert session_client.get(path(target), headers=headers(pair)).status_code == 403
    assert (
        session_client.put(path(target) + "/roles/creator", headers=headers(pair)).status_code
        == 403
    )


def test_browser_ownership_and_csrf(session_client, identities, identity_engine):
    actor, target, _ = identities
    base = "/api/v1/auth/browser"

    def csrf():
        response = session_client.get(base + "/csrf")
        return {"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": response.json()["csrf_token"]}

    assert (
        session_client.post(
            base + "/login",
            json={"email": actor["email"], "password": actor["password"]},
            headers=csrf(),
        ).status_code
        == 200
    )
    own = base + "/users/" + actor["id"]
    other = base + "/users/" + target["id"]
    assert session_client.get(own).status_code == 200
    assert session_client.patch(own, json={"display_name": "Browser viewer"}).status_code == 403
    assert (
        session_client.patch(
            own, json={"display_name": "Browser viewer"}, headers=csrf()
        ).status_code
        == 200
    )
    assert session_client.get(other).status_code == 403
    assert (
        session_client.put(other + "/roles/super_admin", json={}, headers=csrf()).status_code == 403
    )
    assert session_client.get(path(actor)).status_code == 401


def test_concurrent_role_grants_are_idempotent(session_client, identities, identity_engine):
    from fastapi.testclient import TestClient

    actor, target, _ = identities
    add_role(identity_engine, actor, "super_admin")
    pair = auth(session_client, actor)

    def grant(_):
        with TestClient(app) as client:
            return client.put(path(target) + "/roles/creator", headers=headers(pair)).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(grant, range(2))) == [204, 204]
    with Session(identity_engine) as session:
        assert policy.roles_for(session, UUID(target["id"])) == ["creator", "viewer"]


def test_revoked_actor_and_forged_role_claims(
    session_client, identities, identity_engine, session_settings
):
    import jwt

    actor, target, _ = identities
    pair = auth(session_client, actor)
    claims = jwt.decode(pair["access_token"], options={"verify_signature": False})
    claims["roles"] = ["super_admin"]
    claims["permissions"] = ["roles:assign"]
    # Even a validly signed extra claim is not an authorization source.
    forged = jwt.encode(
        claims,
        session_settings.access_signing_key.get_secret_value(),
        algorithm="HS256",
        headers={"typ": "at+jwt"},
    )
    assert (
        session_client.put(
            path(target) + "/roles/super_admin", headers={"Authorization": "Bearer " + forged}
        ).status_code
        == 403
    )
    assert session_client.post("/api/v1/auth/logout", headers=headers(pair)).status_code == 204
    assert session_client.get(path(actor), headers=headers(pair)).status_code == 401


def test_profile_rollback_and_recheck_after_initial_auth(
    session_client, identities, identity_engine, monkeypatch
):
    from app.api import authorization

    actor = identities[0]
    pair = auth(session_client, actor)
    original = authorization.lock_and_reauthenticate

    def revoke_before_lock(session, principal, target_id, settings, **kwargs):
        with Session(identity_engine) as other, other.begin():
            grant = other.scalar(
                select(AccessGrant).where(AccessGrant.user_id == principal.user_id)
            )
            grant.revoked_at = policy.now()
        return original(session, principal, target_id, settings, **kwargs)

    monkeypatch.setattr(authorization, "lock_and_reauthenticate", revoke_before_lock)
    assert (
        session_client.patch(
            path(actor), json={"display_name": "Stale auth"}, headers=headers(pair)
        ).status_code
        == 401
    )
    with Session(identity_engine) as session:
        assert session.get(User, UUID(actor["id"])).display_name == actor["display_name"]


def test_revocation_rechecked_after_initial_role_auth(
    session_client, identities, identity_engine, monkeypatch
):
    from app.api import authorization

    actor, target, _ = identities
    add_role(identity_engine, actor, "super_admin")
    pair = auth(session_client, actor)
    original = authorization.lock_and_reauthenticate

    def remove_before_lock(session, principal, target_id, settings, **kwargs):
        with Session(identity_engine) as other, other.begin():
            role = other.scalar(select(Role).where(Role.code == "super_admin"))
            other.delete(other.get(UserRole, (principal.user_id, role.id)))
        return original(session, principal, target_id, settings, **kwargs)

    monkeypatch.setattr(authorization, "lock_and_reauthenticate", remove_before_lock)
    assert (
        session_client.put(path(target) + "/roles/creator", headers=headers(pair)).status_code
        == 403
    )
    with Session(identity_engine) as session:
        assert policy.roles_for(session, UUID(target["id"])) == ["viewer"]


def test_read_permission_does_not_allow_write(session_client, identities, identity_engine):
    actor, target, _ = identities
    add_role(identity_engine, actor, "creator")
    with Session(identity_engine) as session, session.begin():
        role = session.scalar(select(Role).where(Role.code == "creator"))
        permission = session.scalar(select(Permission).where(Permission.code == "users:read"))
        session.add(RolePermission(role_id=role.id, permission_id=permission.id))
        ids = role.id, permission.id
    try:
        pair = auth(session_client, actor)
        assert session_client.get(path(target), headers=headers(pair)).status_code == 200
        assert (
            session_client.patch(
                path(target), json={"display_name": "Denied"}, headers=headers(pair)
            ).status_code
            == 403
        )
    finally:
        with Session(identity_engine) as session, session.begin():
            session.delete(session.get(RolePermission, ids))


@pytest.mark.parametrize("code", ["creator", "super_admin"])
def test_privileged_revoke_disabled_target(session_client, identities, identity_engine, code):
    actor, target, _ = identities
    add_role(identity_engine, actor, "super_admin")
    add_role(identity_engine, target, code)
    pair = auth(session_client, actor)
    with Session(identity_engine) as session, session.begin():
        session.get(User, UUID(target["id"])).status = "suspended"
    assert (
        session_client.delete(path(target) + "/roles/" + code, headers=headers(pair)).status_code
        == 204
    )
    with Session(identity_engine) as session:
        role = session.scalar(select(Role).where(Role.code == code))
        assert session.get(UserRole, (UUID(target["id"]), role.id)) is None


@pytest.mark.parametrize("operation", ["get", "patch", "put", "delete"])
def test_missing_auth_is_401(session_client, identities, operation):
    resource = path(identities[0])
    if operation == "get":
        response = session_client.get(resource)
    elif operation == "patch":
        response = session_client.patch(resource, json={"display_name": "Denied"})
    else:
        response = getattr(session_client, operation)(resource + "/roles/creator")
    assert response.status_code == 401


def test_real_redis_mutation_limit_cannot_be_bypassed_by_resource_ids(
    session_settings, monkeypatch
):
    from hashlib import sha256

    from fastapi import Request
    from redis import Redis

    from app.services import rate_limits

    redis = Redis.from_url(session_settings.redis_url.get_secret_value())
    monkeypatch.setattr(rate_limits, "get_registration_redis", lambda: redis)
    config = session_settings.model_copy(update={"session_requests_per_window": 1})
    address = "rbac-test-" + uuid4().hex
    scope = sha256(b"identity_mutations").hexdigest()
    keys = [
        "auth:action:" + scope + ":" + kind + ":" + sha256(address.encode()).hexdigest()
        for kind in ("ip", "identity")
    ]

    def request():
        return Request(
            {
                "type": "http",
                "path": "/api/v1/users/" + str(uuid4()),
                "headers": [],
                "client": (address, 1),
            }
        )

    try:
        rate_limits.limit_authorization(request(), config)
        with pytest.raises(HTTPException) as denied:
            rate_limits.limit_authorization(request(), config)
        assert denied.value.status_code == 429
        assert 0 < redis.ttl(keys[0]) <= config.session_window_seconds
    finally:
        redis.delete(*keys)
        redis.close()
