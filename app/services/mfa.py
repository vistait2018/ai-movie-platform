"""MFA mutations require the user lock and a freshly validated session credential."""

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import compare_digest, token_urlsafe
from typing import NoReturn
from uuid import UUID

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.passwords import verify_password
from app.core.settings import Settings
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
from app.schemas.mfa import EnrollmentIssued, RecoveryIssued
from app.services.sessions import active_user, revoke_user_sessions

PRIVILEGED_ROLES = frozenset({"moderator", "finance_admin", "super_admin"})


def now() -> datetime:
    return datetime.now(UTC)


def cipher(settings: Settings) -> Fernet:
    try:
        if settings.mfa_encryption_key is None:
            raise ValueError
        return Fernet(settings.mfa_encryption_key.get_secret_value().encode("ascii"))
    except (ValueError, UnicodeError):
        raise HTTPException(503, "MFA temporarily unavailable") from None


def secret_for(factor: MFAFactor, settings: Settings) -> str:
    try:
        data = json.loads(cipher(settings).decrypt(factor.encrypted_secret))
        if data["user_id"] != str(factor.user_id) or not isinstance(data["secret"], str):
            raise ValueError
        return str(data["secret"])
    except (InvalidToken, ValueError, KeyError, TypeError):
        raise HTTPException(503, "MFA temporarily unavailable") from None


def event(session: Session, user_id: UUID, name: str) -> None:
    session.add(SecurityEvent(subject_user_id=user_id, event=name))


def reject(session: Session, user_id: UUID) -> NoReturn:
    event(session, user_id, "mfa_proof_rejected")
    session.commit()
    raise HTTPException(403, "MFA verification required")


def reauthenticate(session: Session, user: User, password: str) -> None:
    if not active_user(user) or not verify_password(password, user.password_hash):
        reject(session, user.id)


def enroll(
    session: Session, user: User, family: AuthSession, password: str, settings: Settings
) -> EnrollmentIssued:
    reauthenticate(session, user, password)
    factor = session.get(MFAFactor, user.id)
    instant = now()
    if factor is not None:
        if factor.confirmed_at is not None or factor.enrollment_expires_at > instant:
            raise HTTPException(409, "MFA enrollment already exists")
        session.delete(factor)
        session.flush()
    secret = pyotp.random_base32()
    encrypted = cipher(settings).encrypt(
        json.dumps({"user_id": str(user.id), "secret": secret}).encode()
    )
    session.add(
        MFAFactor(
            user_id=user.id,
            encrypted_secret=encrypted,
            enrollment_session_id=family.id,
            enrollment_expires_at=instant + timedelta(seconds=settings.mfa_enrollment_seconds),
            last_counter=-1,
        )
    )
    event(session, user.id, "mfa_enrollment_started")
    session.commit()
    return EnrollmentIssued(
        secret=secret,
        provisioning_uri=pyotp.TOTP(secret).provisioning_uri(
            user.email, issuer_name="AI Movie Platform"
        ),
    )


def consume_totp(factor: MFAFactor, code: str, settings: Settings, instant: datetime) -> bool:
    if len(code) != 6 or not code.isascii() or not code.isdecimal():
        return False
    totp = pyotp.TOTP(secret_for(factor, settings))
    counter = totp.timecode(instant)
    # Store the actual accepted counter, including forward skew; never accept it twice.
    for candidate in (counter - 1, counter, counter + 1):
        if candidate > factor.last_counter and compare_digest(totp.at(candidate * 30), code):
            factor.last_counter = candidate
            return True
    return False


def recovery_digest(user_id: UUID, code: str) -> str:
    # Codes contain 256 random bits; a domain/user-bound SHA-256 digest resists offline guessing.
    return sha256(f"mfa-recovery:{user_id}:{code}".encode()).hexdigest()


def set_assurance(
    session: Session, user: User, family: AuthSession, settings: Settings, instant: datetime
) -> None:
    assurance = session.get(MFAAssurance, family.id)
    if assurance is None:
        assurance = MFAAssurance(session_id=family.id, user_id=user.id)
        session.add(assurance)
    assurance.verified_at = instant
    assurance.expires_at = min(
        instant + timedelta(seconds=settings.mfa_assurance_seconds), family.expires_at
    )


def confirm(
    session: Session, user: User, family: AuthSession, password: str, code: str, settings: Settings
) -> RecoveryIssued:
    reauthenticate(session, user, password)
    factor = session.get(MFAFactor, user.id)
    instant = now()
    if (
        factor is None
        or factor.confirmed_at is not None
        or factor.enrollment_session_id != family.id
        or factor.enrollment_expires_at <= instant
        or not consume_totp(factor, code, settings, instant)
    ):
        reject(session, user.id)
    factor.confirmed_at = instant
    codes = [token_urlsafe(32) for _ in range(8)]
    session.add_all(
        MFARecoveryCode(user_id=user.id, digest=recovery_digest(user.id, value)) for value in codes
    )
    session.flush()
    set_assurance(session, user, family, settings, instant)
    event(session, user.id, "mfa_enrollment_confirmed")
    session.commit()
    return RecoveryIssued(recovery_codes=codes)


def consume_proof(
    session: Session, user: User, password: str, code: str, settings: Settings
) -> None:
    reauthenticate(session, user, password)
    factor = session.get(MFAFactor, user.id)
    instant = now()
    if factor is None or factor.confirmed_at is None:
        reject(session, user.id)
    if consume_totp(factor, code, settings, instant):
        return
    recovery = session.get(MFARecoveryCode, (user.id, recovery_digest(user.id, code)))
    if recovery is None or recovery.consumed_at is not None:
        reject(session, user.id)
    recovery.consumed_at = instant
    event(session, user.id, "mfa_recovery_consumed")


def verify(
    session: Session, user: User, family: AuthSession, password: str, code: str, settings: Settings
) -> None:
    consume_proof(session, user, password, code, settings)
    set_assurance(session, user, family, settings, now())
    event(session, user.id, "mfa_step_up_verified")
    session.commit()


def require_assurance(session: Session, user: User, session_id: UUID | None) -> None:
    family = session.get(AuthSession, session_id) if session_id else None
    assurance = session.get(MFAAssurance, session_id) if session_id else None
    factor = session.get(MFAFactor, user.id)
    instant = now()
    if (
        not active_user(user)
        or family is None
        or family.user_id != user.id
        or family.revoked_at is not None
        or family.expires_at <= instant
        or assurance is None
        or assurance.user_id != user.id
        or assurance.verified_at > instant
        or assurance.expires_at <= instant
        or factor is None
        or factor.confirmed_at is None
    ):
        raise HTTPException(403, "Access denied")


def ensure_factor_removable(session: Session, user_id: UUID) -> None:
    privileged = session.scalar(
        select(UserRole.user_id)
        .join(Role)
        .where(UserRole.user_id == user_id, Role.code.in_(PRIVILEGED_ROLES))
        .limit(1)
    )
    if privileged is not None:
        # Role removal must pass the existing last-admin safeguards before factor retirement.
        raise HTTPException(409, "Remove privileged roles before resetting MFA")


def retire_factor(session: Session, user_id: UUID, actor_id: UUID) -> None:
    ensure_factor_removable(session, user_id)
    session.execute(delete(MFAFactor).where(MFAFactor.user_id == user_id))
    revoke_user_sessions(session, user_id, now(), "mfa_reset")
    event(session, user_id, f"mfa_reset:{actor_id}")
    session.commit()
