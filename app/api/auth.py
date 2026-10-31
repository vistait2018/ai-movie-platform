import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import DatabaseUnavailable, get_db_session
from app.schemas.auth import RegistrationRequest, RegistrationResponse
from app.services.rate_limits import limit_registration
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
        "No login/session is issued. Verification delivery/confirmation follows in Increment 3."
    ),
    responses={
        422: {"description": "Invalid input (sensitive values omitted)"},
        429: {"description": "Registration request limit exceeded"},
        503: {"description": "Registration dependencies unavailable"},
    },
)
def register(
    payload: RegistrationRequest, session: Annotated[Session, Depends(get_db_session)]
) -> RegistrationResponse:
    try:
        register_user(session, payload)
    except (SQLAlchemyError, DatabaseUnavailable) as error:
        logger.warning("registration_unavailable", extra={"error_type": type(error).__name__})
        raise HTTPException(
            status_code=503, detail="Registration temporarily unavailable"
        ) from None
    return RegistrationResponse()
