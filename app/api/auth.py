import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import current_user
from app.core.settings import Settings, get_settings
from app.core.tokens import TokenConfigurationError
from app.db.session import DatabaseUnavailable, get_db_session
from app.models.identity import Role, User, UserRole
from app.schemas.auth import (
    CurrentUser,
    LoginRequest,
    LoginResponse,
    RegistrationRequest,
    RegistrationResponse,
)
from app.services.authentication import authenticate
from app.services.email_delivery import DeliveryUnavailable
from app.services.rate_limits import limit_login, limit_registration
from app.services.registration import register_user

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
logger = logging.getLogger("movie.auth")


@router.post(
    "/register",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RegistrationResponse,
    dependencies=[Depends(limit_registration)],
    summary="Request a pending Viewer account",
    description=(
        "Creates a pending, unverified Viewer account. Existing emails receive the same response. "
        "No login/session is issued. A verification message is queued atomically for new accounts."
    ),
    responses={
        422: {"description": "Invalid input (sensitive values omitted)"},
        429: {"description": "Registration request limit exceeded"},
        503: {"description": "Registration dependencies unavailable"},
    },
)
def register(
    payload: RegistrationRequest,
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RegistrationResponse:
    try:
        register_user(session, payload, settings)
    except (SQLAlchemyError, DatabaseUnavailable, DeliveryUnavailable) as error:
        logger.warning("registration_unavailable", extra={"error_type": type(error).__name__})
        raise HTTPException(
            status_code=503, detail="Registration temporarily unavailable"
        ) from None
    return RegistrationResponse()


@router.post(
    "/login",
    response_model=LoginResponse,
    dependencies=[Depends(limit_login)],
    summary="Authenticate a verified active user",
    description="JSON credentials for web and Flutter. Returns an access bearer token only; "
    "no refresh token, cookie session or logout is provided.",
    responses={
        401: {"description": "Invalid credentials or account not eligible"},
        429: {"description": "Login limit exceeded"},
        503: {"description": "Authentication unavailable"},
    },
)
def login(
    payload: LoginRequest,
    response: Response,
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    try:
        result = authenticate(session, payload, settings)
    except (SQLAlchemyError, DatabaseUnavailable, TokenConfigurationError):
        logger.warning("authentication_unavailable")
        raise HTTPException(503, "Authentication temporarily unavailable") from None
    if result is None:
        raise HTTPException(
            401, "Invalid email or password", headers={"WWW-Authenticate": "Bearer"}
        )
    return result


@router.get(
    "/me",
    response_model=CurrentUser,
    summary="Read the authenticated user's profile",
    responses={
        401: {"description": "Missing, invalid, expired or revoked access"},
        503: {"description": "Authentication unavailable"},
    },
)
def me(
    response: Response,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> CurrentUser:
    response.headers["Cache-Control"] = "no-store"
    roles = session.scalars(
        select(Role.code).join(UserRole).where(UserRole.user_id == user.id)
    ).all()
    return CurrentUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        roles=sorted(roles),
    )
