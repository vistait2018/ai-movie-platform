"""Database-backed, default-deny authorization for existing identity resources."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.models.identity import Permission, Role, RolePermission, User, UserRole
from app.services.mfa import require_assurance
from app.services.sessions import active_user

ROLES = frozenset({"viewer", "creator", "moderator", "finance_admin", "super_admin"})
PERMISSIONS = frozenset(
    {
        "profile:read",
        "profile:update",
        "users:read",
        "users:manage",
        "roles:assign",
        "audit:read",
        "content:moderate",
        "finance:read",
        "projects:manage",
    }
)
logger = logging.getLogger("movie.authorization")


def roles_for(session: Session, user_id: UUID) -> list[str]:
    return sorted(
        session.scalars(
            select(Role.code)
            .join(UserRole)
            .join(User, User.id == UserRole.user_id)
            .where(
                User.id == user_id,
                User.status == "active",
                User.email_verified_at.is_not(None),
                Role.code.in_(ROLES),
            )
        ).all()
    )


def permissions_for(session: Session, user_id: UUID) -> set[str]:
    return set(
        session.scalars(
            select(Permission.code)
            .join(RolePermission)
            .join(Role)
            .join(UserRole)
            .join(User, User.id == UserRole.user_id)
            .where(
                User.id == user_id,
                User.status == "active",
                User.email_verified_at.is_not(None),
                Role.code.in_(ROLES),
                Permission.code.in_(PERMISSIONS),
            )
            .distinct()
        ).all()
    )


def forbidden(user_id: UUID) -> HTTPException:
    logger.info("authorization_denied", extra={"user_id": str(user_id)})
    return HTTPException(403, "Access denied")


def require_role(session: Session, user: User, role: str) -> None:
    if role not in ROLES or role not in roles_for(session, user.id):
        raise forbidden(user.id)


def require_permission(session: Session, user: User, permission: str) -> None:
    if not active_user(user):
        raise HTTPException(401, "Authentication required")
    if permission not in PERMISSIONS or permission not in permissions_for(session, user.id):
        raise forbidden(user.id)


def require_privileged(
    session: Session,
    user: User,
    permission: str,
    settings: Settings,
    *,
    session_id: UUID | None = None,
) -> None:
    require_permission(session, user, permission)
    # No client flag/header or production configuration can fabricate MFA assurance.
    # Production enablement requires explicit acceptance and a separate reviewed change.
    if settings.environment not in {"development", "test"}:
        raise forbidden(user.id)
    require_assurance(session, user, session_id)


def require_owner(
    session: Session,
    user: User,
    owner_id: UUID,
    *,
    action: str,
    settings: Settings,
    session_id: UUID | None = None,
) -> None:
    if action not in {"read", "update"}:
        raise forbidden(user.id)
    if user.id == owner_id:
        require_permission(session, user, "profile:" + action)
    else:
        require_privileged(
            session,
            user,
            "users:" + ("read" if action == "read" else "manage"),
            settings,
            session_id=session_id,
        )


def now() -> datetime:
    return datetime.now(UTC)
