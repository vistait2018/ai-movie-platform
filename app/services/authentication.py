import logging
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.passwords import hash_password, verify_password
from app.core.settings import Settings
from app.core.tokens import encode_access, signing_key
from app.models.identity import AccessGrant, SecurityEvent, User
from app.schemas.auth import LoginRequest, LoginResponse

logger = logging.getLogger("movie.auth")


@lru_cache
def dummy_password_hash() -> str:
    # Same Argon2id work for unknown accounts; this is not an account credential.
    return hash_password(uuid4().hex + uuid4().hex)


def authenticate(
    session: Session, payload: LoginRequest, settings: Settings
) -> LoginResponse | None:
    signing_key(settings)  # Fail closed before accepting credentials if signing is unconfigured.
    result = None
    with session.begin():
        user = session.scalar(
            select(User).where(User.email == str(payload.email)).with_for_update()
        )
        matched = verify_password(
            payload.password.get_secret_value(),
            user.password_hash if user else dummy_password_hash(),
        )
        if not matched or user is None or user.status != "active" or user.email_verified_at is None:
            session.add(
                SecurityEvent(subject_user_id=user.id if user else None, event="login_failed")
            )
        else:
            issued = datetime.now(UTC).replace(microsecond=0)
            expires = issued + timedelta(seconds=settings.access_token_seconds)
            grant_id = uuid4()
            token = encode_access(user.id, grant_id, issued, expires, settings)
            session.add(
                AccessGrant(id=grant_id, user_id=user.id, created_at=issued, expires_at=expires)
            )
            session.add(SecurityEvent(subject_user_id=user.id, event="login_succeeded"))
            user.last_login_at = issued
            result = LoginResponse(access_token=token, expires_in=settings.access_token_seconds)
    logger.info("login_succeeded" if result else "login_failed")
    return result
