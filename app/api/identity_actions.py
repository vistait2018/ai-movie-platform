import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.db.session import DatabaseUnavailable, get_db_session
from app.schemas.auth import (
    ActionConfirmation,
    ActionResponse,
    EmailActionRequest,
    PasswordResetConfirmation,
)
from app.services.email_delivery import DeliveryUnavailable
from app.services.identity_actions import ActionKind, redeem_action, request_action
from app.services.rate_limits import (
    limit_action_confirmation,
    limit_action_request,
    limit_reset_confirmation,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
logger = logging.getLogger("movie.auth")
_REQUEST_MESSAGE = "If the account is eligible, a message will be queued."
_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"description": "Invalid, expired, used or ineligible action"},
    429: {"description": "Request limit exceeded"},
    503: {"description": "Authentication dependencies unavailable"},
}


def perform_request(
    session: Session, email: str, kind: ActionKind, settings: Settings
) -> ActionResponse:
    try:
        request_action(session, email, kind, settings)
    except (SQLAlchemyError, DatabaseUnavailable, DeliveryUnavailable):
        logger.warning("identity_action_unavailable")
        raise HTTPException(503, "Authentication temporarily unavailable") from None
    return ActionResponse(message=_REQUEST_MESSAGE)


def perform_confirmation(
    session: Session, token: str, kind: ActionKind, password: str | None = None
) -> ActionResponse:
    try:
        accepted = redeem_action(session, token, kind, password)
    except (SQLAlchemyError, DatabaseUnavailable):
        logger.warning("identity_action_unavailable")
        raise HTTPException(503, "Authentication temporarily unavailable") from None
    if not accepted:
        raise HTTPException(400, "Invalid or expired action")
    return ActionResponse(
        message="Email verified."
        if kind == "verify_email"
        else "Password reset. Sign in with your new password."
    )


@router.post(
    "/request-verification",
    response_model=ActionResponse,
    status_code=202,
    dependencies=[Depends(limit_action_request)],
    responses=_ERRORS,
    summary="Request verification for an eligible pending account",
)
def request_verification(
    payload: EmailActionRequest,
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ActionResponse:
    return perform_request(session, str(payload.email), "verify_email", settings)


@router.post(
    "/verify-email",
    response_model=ActionResponse,
    dependencies=[Depends(limit_action_confirmation)],
    responses=_ERRORS,
    summary="Redeem a single-use email verification token",
    description="POST the message token in JSON. Never use a token in a URL. No automatic login.",
)
def verify_email(
    payload: ActionConfirmation, session: Annotated[Session, Depends(get_db_session)]
) -> ActionResponse:
    return perform_confirmation(session, payload.token.get_secret_value(), "verify_email")


@router.post(
    "/forgot-password",
    response_model=ActionResponse,
    status_code=202,
    dependencies=[Depends(limit_action_request)],
    responses=_ERRORS,
    summary="Request recovery without disclosing account existence",
)
def forgot_password(
    payload: EmailActionRequest,
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ActionResponse:
    return perform_request(session, str(payload.email), "reset_password", settings)


@router.post(
    "/reset-password",
    response_model=ActionResponse,
    dependencies=[Depends(limit_reset_confirmation)],
    responses=_ERRORS,
    summary="Reset an eligible account password and revoke all access grants",
)
def reset_password(
    payload: PasswordResetConfirmation, session: Annotated[Session, Depends(get_db_session)]
) -> ActionResponse:
    return perform_confirmation(
        session,
        payload.token.get_secret_value(),
        "reset_password",
        payload.new_password.get_secret_value(),
    )
