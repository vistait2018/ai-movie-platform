"""Cookie adapter over the existing authentication/session services."""

import logging
from hashlib import sha256
from secrets import token_urlsafe
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import current_user
from app.api.sessions import perform_logout
from app.core.browser import (
    PATH,
    binding,
    clear_cookies,
    cookie_name,
    issue_csrf,
    read_cookie,
    set_cookie,
    validate_csrf,
)
from app.core.settings import Settings, get_settings
from app.core.tokens import TokenConfigurationError
from app.db.session import DatabaseUnavailable, get_db_session
from app.schemas.auth import LoginRequest, SessionCredentials
from app.services.authentication import authenticate
from app.services.rate_limits import limit_login, limit_logout
from app.services.sessions import rotate_refresh

logger = logging.getLogger("movie.auth")
Config = Annotated[Settings, Depends(get_settings)]
Database = Annotated[Session, Depends(get_db_session)]


def browser_guard(
    request: Request,
    settings: Config,
    x_csrf_token: Annotated[
        str | None, Header(description="Challenge from GET browser/csrf")
    ] = None,
    origin: Annotated[str | None, Header(description="Exact approved browser origin")] = None,
) -> None:
    try:
        validate_csrf(request, settings)
    except TokenConfigurationError:
        raise HTTPException(503, "Authentication temporarily unavailable") from None


router = APIRouter(
    prefix=PATH,
    tags=["Browser authentication"],
    dependencies=[Depends(browser_guard)],
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "Invalid CSRF or origin"},
        429: {"description": "Request limit exceeded"},
        503: {"description": "Authentication unavailable"},
    },
)


def credentials_response(pair: SessionCredentials, settings: Settings) -> Response:
    response = JSONResponse(
        {"authenticated": True, "session_id": str(pair.session_id), "expires_in": pair.expires_in}
    )
    set_cookie(response, "access", pair.access_token, pair.expires_in, settings)
    set_cookie(response, "refresh", pair.refresh_token, pair.refresh_expires_in, settings)
    response.delete_cookie(
        cookie_name("bootstrap", settings),
        path=PATH,
        secure=settings.browser_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/csrf", summary="Obtain a short-lived browser CSRF challenge")
def csrf(request: Request, settings: Config) -> Response:
    response = JSONResponse({})
    bound = binding(request, settings)
    if not bound:
        bootstrap = token_urlsafe(32)
        set_cookie(response, "bootstrap", bootstrap, settings.browser_csrf_seconds, settings)
        bound = sha256(("bootstrap:" + bootstrap).encode()).hexdigest()
    try:
        token = issue_csrf(bound, settings)
    except TokenConfigurationError:
        raise HTTPException(503, "Authentication temporarily unavailable") from None
    # Only CSRF challenges are readable by JavaScript, never authentication credentials.
    response.body = JSONResponse({"csrf_token": token}).body
    response.headers["content-length"] = str(len(response.body))
    return response


@router.post("/login", dependencies=[Depends(limit_login)], summary="Establish browser cookies")
def login(payload: LoginRequest, session: Database, settings: Config) -> Response:
    try:
        pair = authenticate(
            session, payload.model_copy(update={"session_mode": "refresh"}), settings
        )
    except (SQLAlchemyError, DatabaseUnavailable, TokenConfigurationError):
        logger.warning("browser_login_unavailable")
        raise HTTPException(503, "Authentication temporarily unavailable") from None
    if not isinstance(pair, SessionCredentials):
        raise HTTPException(401, "Invalid email or password")
    return credentials_response(pair, settings)


@router.post("/refresh", dependencies=[Depends(limit_logout)], summary="Rotate browser cookies")
def refresh(request: Request, session: Database, settings: Config) -> Response:
    try:
        value = read_cookie(request, "refresh", settings)
        pair = rotate_refresh(session, value, settings) if value else None
    except (SQLAlchemyError, DatabaseUnavailable, TokenConfigurationError):
        logger.warning("browser_refresh_unavailable")
        raise HTTPException(503, "Authentication temporarily unavailable") from None
    if pair is None:
        response = JSONResponse({"detail": "Authentication required"}, status_code=401)
        clear_cookies(response, settings)
        return response
    return credentials_response(pair, settings)


def browser_credentials(request: Request, settings: Settings) -> HTTPAuthorizationCredentials:
    token = read_cookie(request, "access", settings)
    if not token:
        raise HTTPException(401, "Authentication required")
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@router.get("/session", summary="Read safe authenticated browser session metadata")
def status(request: Request, session: Database, settings: Config) -> dict[str, object]:
    user = current_user(browser_credentials(request, settings), session, settings)
    return {"authenticated": True, "user_id": str(user.id), "status": user.status}


def end_session(
    request: Request, session: Session, settings: Settings, *, everywhere: bool
) -> Response:
    response: Response
    try:
        perform_logout(
            browser_credentials(request, settings), session, settings, everywhere=everywhere
        )
    except HTTPException as error:
        if error.status_code != 401:
            raise
        response = JSONResponse({"detail": "Authentication required"}, status_code=401)
    else:
        response = Response(status_code=204)
    clear_cookies(response, settings)
    return response


@router.post("/logout", dependencies=[Depends(limit_logout)], status_code=204)
def logout(request: Request, session: Database, settings: Config) -> Response:
    return end_session(request, session, settings, everywhere=False)


@router.post("/logout-all", dependencies=[Depends(limit_logout)], status_code=204)
def logout_all(request: Request, session: Database, settings: Config) -> Response:
    return end_session(request, session, settings, everywhere=True)
