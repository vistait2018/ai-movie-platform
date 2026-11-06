"""Account lifecycle changes; caller must authorize and hold administration/user locks."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.identity import MFAFactor, Role, SecurityEvent, User, UserRole
from app.services import authorization as policy
from app.services.identity_actions import consume_actions
from app.services.mfa import PRIVILEGED_ROLES
from app.services.sessions import active_user, revoke_user_sessions


def change_status(session: Session, actor_id: UUID, target: User, status: str) -> None:
    if actor_id == target.id:
        raise policy.forbidden(actor_id)
    if status not in {"pending", "active", "suspended", "deactivated"}:
        raise HTTPException(422, "Invalid account status")
    if status == target.status:
        return
    if (status == "active" and target.email_verified_at is None) or (
        status == "pending" and target.email_verified_at is not None
    ):
        raise HTTPException(409, "Account status conflicts with email verification")
    assigned = set(
        session.scalars(select(Role.code).join(UserRole).where(UserRole.user_id == target.id))
    )
    if status == "active" and assigned & PRIVILEGED_ROLES:
        factor = session.get(MFAFactor, target.id)
        if factor is None or factor.confirmed_at is None:
            raise HTTPException(409, "Privileged accounts require confirmed MFA before activation")
    if status != "active" and active_user(target) and "super_admin" in assigned:
        count = session.scalar(
            select(func.count())
            .select_from(UserRole)
            .join(Role)
            .join(User, User.id == UserRole.user_id)
            .where(
                Role.code == "super_admin",
                User.status == "active",
                User.email_verified_at.is_not(None),
            )
        )
        if count is None or count <= 1:
            raise HTTPException(409, "Status change conflicts with administrator safeguards")
    target.status = status
    instant = policy.now()
    revoke_user_sessions(session, target.id, instant, "status_changed")
    consume_actions(session, target.id, instant)
    session.add(
        SecurityEvent(subject_user_id=target.id, event=f"status_changed:{actor_id}:{status}")
    )
