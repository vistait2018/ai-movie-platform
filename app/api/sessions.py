import logging
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import bearer
from app.core.settings import Settings, get_settings
from app.core.tokens import TokenConfigurationError
from app.db.session import DatabaseUnavailable, get_db_session
from app.schemas.auth import RefreshRequest, SessionCredentials
from app.services.rate_limits import limit_logout, limit_refresh
from app.services.sessions import logout_access, rotate_refresh

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
logger = logging.getLogger("movie.auth")
_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication required"},
    429: {"description": "Request limit exceeded"},
    503: {"description": "Authentication unavailable"},
}


def denied() -> HTTPException:
    return HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})


@router.post(
    "/refresh",
    response_model=SessionCredentials,
    dependencies=[Depends(limit_refresh)],
    responses=_ERRORS,
    summary="Atomically rotate refresh and access credentials",
    description="Strict reuse detection revokes the family, including any concurrent successor. "
    "Clients must serialize refresh operations. JSON transport only; no cookies.",
)
def refresh(
    payload: RefreshRequest,
    response: Response,
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionCredentials:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    try:
        result = rotate_refresh(session, payload.refresh_token.get_secret_value(), settings)
    except (SQLAlchemyError, DatabaseUnavailable, TokenConfigurationError):
        logger.warning("refresh_unavailable")
        raise HTTPException(503, "Authentication temporarily unavailable") from None
    if result is None:
        raise denied()
    return result


def perform_logout(
    credentials: HTTPAuthorizationCredentials | None,
    session: Session,
    settings: Settings,
    *,
    everywhere: bool,
) -> None:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise denied()
    try:
        accepted = logout_access(session, credentials.credentials, settings, everywhere=everywhere)
    except jwt.InvalidTokenError:
        raise denied() from None
    except (SQLAlchemyError, DatabaseUnavailable, TokenConfigurationError):
        logger.warning("logout_unavailable")
        raise HTTPException(503, "Authentication temporarily unavailable") from None
    if not accepted:
        raise denied()


@router.post(
    "/logout",
    status_code=204,
    dependencies=[Depends(limit_logout)],
    responses=_ERRORS,
    summary="Revoke the current access grant/session",
    description="Use current access Bearer. Repeating logout with the same unexpired signed "
    "credential is safe; obsolete rotation-revoked credentials cannot kill a live family.",
)
def logout(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    perform_logout(credentials, session, settings, everywhere=False)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post(
    "/logout-all",
    status_code=204,
    dependencies=[Depends(limit_logout)],
    responses=_ERRORS,
    summary="Revoke every session and legacy grant for the authenticated user",
)
def logout_all(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    perform_logout(credentials, session, settings, everywhere=True)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
