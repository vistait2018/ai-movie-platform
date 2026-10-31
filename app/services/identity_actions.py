import logging
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.passwords import hash_password
from app.core.settings import Settings
from app.models.identity import AccessGrant, AuthAction, EmailOutbox, SecurityEvent, User
from app.services.email_delivery import EmailDelivery, get_delivery

ActionKind = Literal["verify_email", "reset_password"]
logger = logging.getLogger("movie.auth")


def digest_action(kind: ActionKind, value: str) -> str:
    return sha256((kind + ":" + value).encode()).hexdigest()


def eligible(user: User, kind: ActionKind) -> bool:
    if kind == "verify_email":
        return user.status == "pending" and user.email_verified_at is None
    return user.status == "active" and user.email_verified_at is not None


def consume_actions(
    session: Session, user_id: UUID, now: datetime, kind: ActionKind | None = None
) -> None:
    conditions = [AuthAction.user_id == user_id]
    if kind is not None:
        conditions.append(AuthAction.kind == kind)
    session.execute(
        delete(EmailOutbox).where(
            EmailOutbox.action_id.in_(select(AuthAction.id).where(*conditions))
        )
    )
    session.execute(
        update(AuthAction)
        .where(*conditions, AuthAction.consumed_at.is_(None))
        .values(consumed_at=now)
    )


def issue_action(
    session: Session,
    user_id: UUID,
    email: str,
    kind: ActionKind,
    settings: Settings,
    delivery: EmailDelivery,
) -> None:
    """Caller owns the user row lock (or its newly inserted row) for serialized issuance."""
    now = datetime.now(UTC)
    previous = session.scalar(
        select(AuthAction)
        .where(
            AuthAction.user_id == user_id,
            AuthAction.kind == kind,
            AuthAction.consumed_at.is_(None),
            AuthAction.expires_at > now,
        )
        .order_by(AuthAction.created_at.desc())
        .limit(1)
    )
    if (
        previous is not None
        and (now - previous.created_at).total_seconds() < settings.action_resend_seconds
    ):
        return
    consume_actions(session, user_id, now, kind)
    value = token_urlsafe(32)
    lifetime = (
        settings.verification_seconds if kind == "verify_email" else settings.password_reset_seconds
    )
    expires = now + timedelta(seconds=lifetime)
    action_id = uuid4()
    session.add(
        AuthAction(
            id=action_id,
            user_id=user_id,
            kind=kind,
            recipient=email,
            token_digest=digest_action(kind, value),
            created_at=now,
            expires_at=expires,
        )
    )
    session.flush()  # Explicit FK ordering without ORM relationships.
    delivery.enqueue(
        session,
        action_id,
        {
            "recipient": email,
            "purpose": kind,
            "token": value,
            "expires_at": expires.isoformat(),
            "confirmation_endpoint": "/api/v1/auth/verify-email"
            if kind == "verify_email"
            else "/api/v1/auth/reset-password",
        },
    )


def request_action(session: Session, email: str, kind: ActionKind, settings: Settings) -> None:
    delivery = get_delivery(settings)  # Same unavailable response for known/unknown users.
    with session.begin():
        user = session.scalar(select(User).where(User.email == email).with_for_update())
        if user is not None and eligible(user, kind):
            issue_action(session, user.id, user.email, kind, settings, delivery)
        session.add(
            SecurityEvent(subject_user_id=user.id if user else None, event=kind + "_requested")
        )
    logger.info("identity_action_requested")


def redeem_action(
    session: Session, value: str, kind: ActionKind, new_password: str | None = None
) -> bool:
    # Password work is bounded/validated before this call; perform it for invalid reset tokens too.
    encoded = hash_password(new_password) if kind == "reset_password" and new_password else None
    accepted = False
    with session.begin():
        found = session.execute(
            select(AuthAction.id, AuthAction.user_id).where(
                AuthAction.token_digest == digest_action(kind, value),
                AuthAction.kind == kind,
            )
        ).one_or_none()
        user = None
        action = None
        if found is not None:
            # Consistent user -> action lock order also serializes resend/reset/login races.
            user = session.scalar(select(User).where(User.id == found.user_id).with_for_update())
            action = session.scalar(
                select(AuthAction).where(AuthAction.id == found.id).with_for_update()
            )
        now = datetime.now(UTC)  # Re-evaluate expiry only after any concurrent lock wait.
        if (
            user is not None
            and action is not None
            and action.consumed_at is None
            and action.expires_at > now
            and action.recipient == user.email
            and eligible(user, kind)
            and (kind != "reset_password" or encoded is not None)
        ):
            if kind == "verify_email":
                user.email_verified_at = now
                user.status = "active"
                consume_actions(session, user.id, now, kind)
            else:
                if encoded is None:
                    raise RuntimeError("Validated reset password required")
                user.password_hash = encoded
                session.execute(
                    update(AccessGrant)
                    .where(
                        AccessGrant.user_id == user.id,
                        AccessGrant.revoked_at.is_(None),
                    )
                    .values(revoked_at=now)
                )
                consume_actions(session, user.id, now)
            accepted = True
        session.add(
            SecurityEvent(
                subject_user_id=user.id if user else None,
                event=kind + ("_completed" if accepted else "_rejected"),
            )
        )
    logger.info("identity_action_completed" if accepted else "identity_action_rejected")
    return accepted
