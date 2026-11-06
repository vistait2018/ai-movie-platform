"""Refresh and revocation mutations serialize on the user row."""

import logging
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.core.tokens import decode_access, encode_access, signing_key
from app.models.identity import AccessGrant, AuthSession, RefreshCredential, SecurityEvent, User
from app.schemas.auth import SessionCredentials

logger = logging.getLogger("movie.auth")


def refresh_digest(value: str) -> str:
    return sha256(("refresh:" + value).encode()).hexdigest()


def active_user(user: User) -> bool:
    return user.status == "active" and user.email_verified_at is not None


def active_access(
    user: User, grant: AccessGrant, family: AuthSession | None, now: datetime
) -> bool:
    return (
        active_user(user)
        and grant.revoked_at is None
        and grant.expires_at > now
        and (
            grant.session_id is None
            or (
                family is not None
                and family.user_id == user.id
                and family.revoked_at is None
                and family.expires_at > now
            )
        )
    )


def issue_pair(
    session: Session,
    user: User,
    family: AuthSession,
    settings: Settings,
    now: datetime,
    parent_id: UUID | None = None,
) -> SessionCredentials:
    value = token_urlsafe(48)
    access_expiry = min(now + timedelta(seconds=settings.access_token_seconds), family.expires_at)
    refresh_expiry = min(now + timedelta(seconds=settings.refresh_token_seconds), family.expires_at)
    grant_id = uuid4()
    encoded = encode_access(user.id, grant_id, now, access_expiry, settings)
    session.add(
        RefreshCredential(
            id=uuid4(),
            session_id=family.id,
            parent_id=parent_id,
            token_digest=refresh_digest(value),
            created_at=now,
            expires_at=refresh_expiry,
        )
    )
    session.add(
        AccessGrant(
            id=grant_id,
            user_id=user.id,
            session_id=family.id,
            created_at=now,
            expires_at=access_expiry,
        )
    )
    return SessionCredentials(
        access_token=encoded,
        expires_in=int((access_expiry - now).total_seconds()),
        session_id=family.id,
        refresh_token=value,
        refresh_expires_in=int((refresh_expiry - now).total_seconds()),
    )


def start_session(
    session: Session, user: User, settings: Settings, now: datetime
) -> SessionCredentials:
    family = AuthSession(
        id=uuid4(),
        user_id=user.id,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.refresh_session_seconds),
    )
    session.add(family)
    session.flush()
    result = issue_pair(session, user, family, settings, now)
    session.add(SecurityEvent(subject_user_id=user.id, event="session_started"))
    return result


def revoke_family(session: Session, family: AuthSession, now: datetime, reason: str) -> None:
    if family.revoked_at is None:
        family.revoked_at = now
        family.revoked_reason = reason
        session.add(
            SecurityEvent(subject_user_id=family.user_id, event="session_revoked_" + reason)
        )
    session.execute(
        update(RefreshCredential)
        .where(RefreshCredential.session_id == family.id, RefreshCredential.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    session.execute(
        update(AccessGrant)
        .where(AccessGrant.session_id == family.id, AccessGrant.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def revoke_user_sessions(session: Session, user_id: UUID, now: datetime, reason: str) -> None:
    # Caller owns the user row lock. Account revocation also includes legacy grants.
    session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason=reason)
    )
    session.execute(
        update(RefreshCredential)
        .where(
            RefreshCredential.session_id.in_(
                select(AuthSession.id).where(AuthSession.user_id == user_id)
            ),
            RefreshCredential.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    session.execute(
        update(AccessGrant)
        .where(AccessGrant.user_id == user_id, AccessGrant.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    session.add(SecurityEvent(subject_user_id=user_id, event="sessions_revoked_" + reason))


def rotate_refresh(session: Session, value: str, settings: Settings) -> SessionCredentials | None:
    signing_key(settings)
    result = None
    event_name = "refresh_rejected"
    user_id = None
    family_id = None
    with session.begin():
        found = session.execute(
            select(RefreshCredential.id, RefreshCredential.session_id, AuthSession.user_id)
            .join(AuthSession, AuthSession.id == RefreshCredential.session_id)
            .where(RefreshCredential.token_digest == refresh_digest(value))
        ).one_or_none()
        if found is not None:
            user = session.scalar(select(User).where(User.id == found.user_id).with_for_update())
            family = session.scalar(
                select(AuthSession).where(AuthSession.id == found.session_id).with_for_update()
            )
            credential = session.scalar(
                select(RefreshCredential).where(RefreshCredential.id == found.id).with_for_update()
            )
            now = datetime.now(UTC).replace(microsecond=0)
            if user is not None and family is not None and credential is not None:
                user_id, family_id = user.id, family.id
                if credential.consumed_at is not None:
                    revoke_family(session, family, now, "reuse")
                    event_name = "refresh_reuse_detected"
                elif not active_user(user):
                    revoke_family(session, family, now, "account_unavailable")
                elif family.revoked_at is not None or credential.revoked_at is not None:
                    revoke_family(session, family, now, "credential_revoked")
                elif family.expires_at <= now or credential.expires_at <= now:
                    revoke_family(session, family, now, "expired")
                else:
                    credential.consumed_at = now
                    session.execute(
                        update(AccessGrant)
                        .where(
                            AccessGrant.session_id == family.id, AccessGrant.revoked_at.is_(None)
                        )
                        .values(revoked_at=now)
                    )
                    result = issue_pair(session, user, family, settings, now, credential.id)
                    event_name = "refresh_rotated"
        session.add(SecurityEvent(subject_user_id=user_id, event=event_name))
    metadata = {
        "user_id": str(user_id) if user_id else None,
        "session_id": str(family_id) if family_id else None,
    }
    if event_name == "refresh_reuse_detected":
        logger.warning(event_name, extra=metadata)
    else:
        logger.info(event_name, extra=metadata)
    return result


def logout_access(
    session: Session, token: str, settings: Settings, *, everywhere: bool = False
) -> bool:
    user_id, grant_id, expiry = decode_access(token, settings)
    accepted = False
    event_name = "logout_all" if everywhere else "logout"
    with session.begin():
        user = session.scalar(select(User).where(User.id == user_id).with_for_update())
        grant = session.scalar(
            select(AccessGrant).where(AccessGrant.id == grant_id, AccessGrant.user_id == user_id)
        )
        now = datetime.now(UTC)
        if user is None or grant is None:
            accepted = not everywhere
        else:
            family = (
                session.scalar(
                    select(AuthSession).where(AuthSession.id == grant.session_id).with_for_update()
                )
                if grant.session_id
                else None
            )
            if everywhere:
                if (
                    active_access(user, grant, family, now)
                    and int(grant.expires_at.timestamp()) == expiry
                ):
                    revoke_user_sessions(session, user.id, now, "logout_all")
                    accepted = True
            elif family is not None and family.revoked_at is not None:
                accepted = True
            elif grant.revoked_at is None and int(grant.expires_at.timestamp()) == expiry:
                if family is None and grant.session_id is None:
                    grant.revoked_at = now
                    accepted = True
                elif family is not None and family.user_id == user.id:
                    revoke_family(session, family, now, "logout")
                    accepted = True
            elif family is None and grant.session_id is None and grant.revoked_at is not None:
                accepted = True
            session.add(
                SecurityEvent(
                    subject_user_id=user.id, event=event_name if accepted else "logout_rejected"
                )
            )
    logger.info(event_name if accepted else "logout_rejected", extra={"user_id": str(user_id)})
    return accepted
