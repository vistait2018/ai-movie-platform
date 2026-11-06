"""Explicit operator-only initial administrator provisioning; no public endpoint."""

import argparse
from getpass import getpass
from uuid import UUID

from fastapi import Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.db.session import get_engine
from app.models.identity import Role, SecurityEvent, User, UserRole
from app.services import mfa
from app.services.rate_limits import check_action_limits
from app.services.sessions import active_user, revoke_user_sessions


def bootstrap(
    session: Session,
    user_id: UUID,
    password: str,
    code: str,
    settings: Settings,
    *,
    confirmed: bool,
) -> None:
    # Production/staging provisioning is intentionally unavailable pending explicit acceptance.
    if not confirmed or settings.environment not in {"development", "test"}:
        raise ValueError("Explicit development bootstrap confirmation required")
    with session.begin():
        session.execute(text("SELECT pg_advisory_xact_lock(724019312)"))
        role = session.scalar(select(Role).where(Role.code == "super_admin"))
        if role is None:
            raise ValueError("Role seed unavailable")
        if (
            session.scalar(select(UserRole.user_id).where(UserRole.role_id == role.id).limit(1))
            is not None
        ):
            raise ValueError("An administrator already exists")
        if (
            session.scalar(
                select(SecurityEvent.id)
                .where(SecurityEvent.event == "initial_admin_provisioned")
                .limit(1)
            )
            is not None
        ):
            raise ValueError("Initial provisioning has already occurred")
        user = session.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None or not active_user(user):
            raise ValueError("An active verified account is required")
        # Requires the existing account password AND a fresh TOTP (not a recovery code).
        mfa.reauthenticate(session, user, password)
        factor = session.get(mfa.MFAFactor, user.id)
        if (
            factor is None
            or factor.confirmed_at is None
            or not mfa.consume_totp(factor, code, settings, mfa.now())
        ):
            mfa.reject(session, user.id)
        session.add(UserRole(user_id=user.id, role_id=role.id))
        revoke_user_sessions(session, user.id, mfa.now(), "role_changed")
        mfa.event(session, user.id, "initial_admin_provisioned")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=UUID, required=True)
    parser.add_argument("--confirm-initial-development-admin", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if settings.environment != "development" or not args.confirm_initial_development_admin:
        parser.error("Only explicitly confirmed development bootstrap is available")
    try:
        # Trusted local operator identity; shares the persistent account budget with MFA APIs.
        check_action_limits(
            Request(
                {
                    "type": "http",
                    "path": "/operator/initial-admin",
                    "headers": [],
                    "client": ("local-operator", 0),
                }
            ),
            str(args.user_id),
            settings,
            settings.mfa_requests_per_window,
            window_seconds=settings.mfa_window_seconds,
            scope_name="mfa_mutations",
        )
        password = getpass("Existing account password: ")
        code = getpass("Fresh authenticator code: ")
        with Session(get_engine()) as session:
            bootstrap(session, args.user_id, password, code, settings, confirmed=True)
    except Exception:
        print("Administrator provisioning refused or unavailable; no sensitive details displayed.")
        return 1
    print("Initial administrator provisioned; existing sessions revoked. Sign in and verify MFA.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
