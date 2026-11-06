from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_authorization import (
    add_role,
    auth,
    headers,
    path,
)
from test_authorization import (
    identities as identities,
)
from test_authorization import (
    isolated_authorization_limits as isolated_authorization_limits,
)
from test_authorization import (
    isolated_mfa_limits as isolated_mfa_limits,
)
from test_authorization import (
    session_client as session_client,
)
from test_authorization import (
    session_settings as session_settings,
)

from app.core.settings import get_settings
from app.main import app
from app.models.identity import (
    AuthAction,
    MFAAssurance,
    Permission,
    Role,
    RolePermission,
    SecurityEvent,
    User,
    UserRole,
)

pytestmark = pytest.mark.integration


def update(client, target, pair, status):
    return client.patch(path(target) + "/status", headers=headers(pair), json={"status": status})


@pytest.mark.parametrize("status", ["suspended", "deactivated"])
def test_disable_reactivate_revokes_all_credentials_and_actions(
    session_client, identities, identity_engine, status
):
    actor, target, _ = identities
    add_role(identity_engine, actor, "super_admin")
    admin, recipient = auth(session_client, actor), auth(session_client, target)
    instant = datetime.now(UTC)
    with Session(identity_engine) as session, session.begin():
        action = AuthAction(
            id=uuid4(),
            user_id=UUID(target["id"]),
            kind="reset_password",
            recipient=target["email"],
            token_digest=uuid4().hex + uuid4().hex,
            created_at=instant,
            expires_at=instant + timedelta(minutes=5),
        )
        action_id = action.id
        session.add(action)
    response = update(session_client, target, admin, status)
    assert response.status_code == 200 and response.json()["status"] == status
    assert response.headers["cache-control"] == "no-store"
    assert session_client.get(path(target), headers=headers(recipient)).status_code == 401
    assert (
        session_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": recipient["refresh_token"]}
        ).status_code
        == 401
    )
    assert (
        session_client.post(
            "/api/v1/auth/login", json={"email": target["email"], "password": target["password"]}
        ).status_code
        == 401
    )
    with Session(identity_engine) as session:
        assert session.get(AuthAction, action_id).consumed_at is not None
        assert (
            session.scalar(
                select(SecurityEvent.id).where(
                    SecurityEvent.subject_user_id == UUID(target["id"]),
                    SecurityEvent.event == f"status_changed:{actor['id']}:{status}",
                )
            )
            is not None
        )
    assert update(session_client, target, admin, "active").status_code == 200
    fresh = auth(session_client, target)
    assert session_client.get(path(target), headers=headers(fresh)).status_code == 200
    assert session_client.get(path(target), headers=headers(recipient)).status_code == 401
    # Idempotent status changes preserve fresh sessions.
    assert update(session_client, target, admin, "active").status_code == 200
    assert session_client.get(path(target), headers=headers(fresh)).status_code == 200


@pytest.mark.parametrize("code", [None, "creator", "moderator", "finance_admin", "admin"])
@pytest.mark.parametrize("exists", [True, False])
def test_permission_boundary_no_existence_disclosure(
    session_client, identities, identity_engine, code, exists
):
    actor, target, _ = identities
    if code:
        add_role(identity_engine, actor, code)
    pair = auth(session_client, actor)
    if not exists:
        target = {"id": str(uuid4())}
    response = update(session_client, target, pair, "suspended")
    assert response.status_code == 403 and response.json() == {"detail": "Access denied"}


def test_status_requires_mfa_and_rejects_self_mass_assignment_and_bad_states(
    session_client, identities, identity_engine
):
    from test_sessions import login

    actor, target, _ = identities
    add_role(identity_engine, actor, "super_admin")
    pair = login(session_client, {"email": actor["email"], "password": actor["password"]})
    assert update(session_client, target, pair, "suspended").status_code == 403
    admin = auth(session_client, actor)
    assert update(session_client, actor, admin, "suspended").status_code == 403
    assert update(session_client, {"id": str(uuid4())}, admin, "suspended").status_code == 404
    assert update(session_client, target, admin, "unknown").status_code == 422
    assert update(session_client, target, admin, "pending").status_code == 409
    assert (
        session_client.patch(
            path(target) + "/status",
            headers=headers(admin),
            json={"status": "suspended", "roles": ["super_admin"]},
        ).status_code
        == 422
    )
    with Session(identity_engine) as session, session.begin():
        assurance = session.get(MFAAssurance, UUID(admin["session_id"]))
        assurance.verified_at = datetime.now(UTC) - timedelta(minutes=10)
        assurance.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    assert update(session_client, target, admin, "suspended").status_code == 403


def test_pending_account_cannot_be_administratively_verified(
    session_client, identities, identity_engine
):
    actor, target, _ = identities
    add_role(identity_engine, actor, "super_admin")
    admin = auth(session_client, actor)
    with Session(identity_engine) as session, session.begin():
        user = session.get(User, UUID(target["id"]))
        user.status, user.email_verified_at = "pending", None
    assert update(session_client, target, admin, "active").status_code == 409
    assert update(session_client, target, admin, "suspended").status_code == 200
    assert update(session_client, target, admin, "pending").status_code == 200
    with Session(identity_engine) as session:
        assert session.get(User, UUID(target["id"])).email_verified_at is None


def test_privileged_reactivation_requires_confirmed_factor(
    session_client, identities, identity_engine
):
    actor, target, _ = identities
    add_role(identity_engine, actor, "super_admin")
    add_role(identity_engine, target, "moderator")
    admin = auth(session_client, actor)
    assert update(session_client, target, admin, "suspended").status_code == 200
    assert update(session_client, target, admin, "active").status_code == 409
    assert (
        session_client.delete(path(target) + "/roles/moderator", headers=headers(admin)).status_code
        == 204
    )
    assert update(session_client, target, admin, "active").status_code == 200


def test_pending_resume_requires_new_email_action(
    session_client, identities, identity_engine, session_settings
):
    from app.dev_outbox import local_messages

    actor, target, _ = identities
    add_role(identity_engine, actor, "super_admin")
    admin = auth(session_client, actor)
    with Session(identity_engine) as session, session.begin():
        user = session.get(User, UUID(target["id"]))
        user.status, user.email_verified_at = "pending", None
    with Session(identity_engine) as session:
        old = local_messages(session, target["email"], session_settings, confirmed=True)[0]["token"]
    assert update(session_client, target, admin, "suspended").status_code == 200
    assert update(session_client, target, admin, "pending").status_code == 200
    assert session_client.post("/api/v1/auth/verify-email", json={"token": old}).status_code == 400
    assert (
        session_client.post(
            "/api/v1/auth/request-verification", json={"email": target["email"]}
        ).status_code
        == 202
    )
    with Session(identity_engine) as session:
        fresh = local_messages(session, target["email"], session_settings, confirmed=True)[0][
            "token"
        ]
    assert fresh != old
    assert (
        session_client.post("/api/v1/auth/verify-email", json={"token": fresh}).status_code == 200
    )


def test_last_admin_suspension_guard(session_client, identities, identity_engine):
    actor, target, _ = identities
    add_role(identity_engine, actor, "creator")
    add_role(identity_engine, target, "super_admin")
    with Session(identity_engine) as session, session.begin():
        creator = session.scalar(select(Role).where(Role.code == "creator"))
        permission = session.scalar(select(Permission).where(Permission.code == "users:manage"))
        link_id = (creator.id, permission.id)
        session.add(RolePermission(role_id=creator.id, permission_id=permission.id))
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
        assert update(session_client, target, pair, "suspended").status_code == 409
        assert update(session_client, target, pair, "deactivated").status_code == 409
    finally:
        with Session(identity_engine) as session, session.begin():
            session.delete(session.get(RolePermission, link_id))
            for uid, status in previous:
                session.get(User, uid).status = status


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_status_environment_gate(
    session_client, identities, identity_engine, session_settings, environment
):
    actor, target, _ = identities
    add_role(identity_engine, actor, "super_admin")
    pair = auth(session_client, actor)
    app.dependency_overrides[get_settings] = lambda: session_settings.model_copy(
        update={"environment": environment}
    )
    assert update(session_client, target, pair, "suspended").status_code == 403


def test_status_rollback_and_stale_actor(session_client, identities, identity_engine, monkeypatch):
    from app.api import authorization

    actor, target, _ = identities
    add_role(identity_engine, actor, "super_admin")
    pair, recipient = auth(session_client, actor), auth(session_client, target)

    def reject(session):
        raise SQLAlchemyError("private-rollback")

    event.listen(Session, "before_commit", reject)
    try:
        response = update(session_client, target, pair, "suspended")
        assert response.status_code == 503 and "private" not in response.text
    finally:
        event.remove(Session, "before_commit", reject)
    assert session_client.get(path(target), headers=headers(recipient)).status_code == 200
    original = authorization.lock_and_reauthenticate

    def revoke_before_lock(session, principal, target_id, settings, **kwargs):
        with Session(identity_engine) as other, other.begin():
            other.get(User, principal.user_id).status = "suspended"
        return original(session, principal, target_id, settings, **kwargs)

    monkeypatch.setattr(authorization, "lock_and_reauthenticate", revoke_before_lock)
    assert update(session_client, target, pair, "suspended").status_code == 401


def test_browser_status_csrf_and_mutual_suspension(session_client, identities, identity_engine):
    actor, target, _ = identities
    for account in (actor, target):
        add_role(identity_engine, account, "super_admin")
    first, second = auth(session_client, actor), auth(session_client, target)
    base = "/api/v1/auth/browser"
    csrf = session_client.get(base + "/csrf").json()["csrf_token"]
    origin = {"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": csrf}
    assert (
        session_client.post(
            base + "/login",
            headers=origin,
            json={"email": actor["email"], "password": actor["password"]},
        ).status_code
        == 200
    )
    resource = base + "/users/" + target["id"] + "/status"
    assert session_client.patch(resource, json={"status": "suspended"}).status_code == 403

    def browser_headers():
        return {
            "Origin": "http://127.0.0.1:8000",
            "X-CSRF-Token": session_client.get(base + "/csrf").json()["csrf_token"],
        }

    verified = session_client.post(
        base + "/mfa/verify",
        headers=browser_headers(),
        json={"password": actor["password"], "code": actor["mfa_recovery"].pop()},
    )
    assert verified.status_code == 204
    assert (
        session_client.patch(
            resource, headers=browser_headers(), json={"status": "active"}
        ).status_code
        == 200
    )
    # Both valid MFA administrators race; the second must reauthenticate after locking.
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(update, session_client, target, first, "suspended")
        two = pool.submit(update, session_client, actor, second, "suspended")
        assert sorted([one.result().status_code, two.result().status_code]) == [200, 401]
