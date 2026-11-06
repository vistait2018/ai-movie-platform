import logging
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.core.tokens import TokenConfigurationError, decode_access
from app.db.session import get_db_session
from app.models.identity import AccessGrant, User

bearer = HTTPBearer(auto_error=False, description="Short-lived access token returned by login")
logger = logging.getLogger("movie.auth")


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    rejected = HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise rejected
    try:
        user_id, grant_id, expiry = decode_access(credentials.credentials, settings)
        pair = session.execute(
            select(User, AccessGrant)
            .join(AccessGrant, AccessGrant.user_id == User.id)
            .where(User.id == user_id, AccessGrant.id == grant_id)
        ).one_or_none()
        if pair is not None:
            user, grant = pair
            if (
                user.status == "active"
                and user.email_verified_at is not None
                and grant.revoked_at is None
                and grant.expires_at > datetime.now(UTC)
                and int(grant.expires_at.timestamp()) == expiry
            ):
                return user
    except jwt.InvalidTokenError:
        pass
    except (TokenConfigurationError, SQLAlchemyError):
        logger.warning("authentication_unavailable")
        raise HTTPException(503, "Authentication temporarily unavailable") from None
    logger.info("access_rejected")
    raise rejected
