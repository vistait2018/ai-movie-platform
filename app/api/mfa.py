"""Bearer and CSRF-protected browser MFA adapters over shared services."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.authorization import (
    Config,
    Database,
    Principal,
    bearer_principal,
    browser_principal,
    execute,
    lock_and_reauthenticate,
)
from app.api.browser import browser_guard
from app.api.dependencies import AuthenticationContext, authenticated_context
from app.models.identity import User
from app.schemas.mfa import EnrollmentIssued, MFAProof, Reauthentication, RecoveryIssued
from app.services import authorization as policy
from app.services import mfa
from app.services.rate_limits import check_action_limits


def make_router(
    prefix: str, authentication: Callable[..., Principal], *, browser: bool
) -> APIRouter:
    router = APIRouter(
        prefix=prefix,
        tags=["Multi-factor authentication"],
        dependencies=[Depends(browser_guard)] if browser else [],
    )
    Actor = Annotated[Principal, Depends(authentication)]

    def limited_actor(request: Request, actor: Actor, settings: Config) -> Principal:
        check_action_limits(
            request,
            str(actor.user_id),
            settings,
            settings.mfa_requests_per_window,
            window_seconds=settings.mfa_window_seconds,
            scope_name="mfa_mutations",
        )
        return actor

    Limited = Annotated[Principal, Depends(limited_actor)]

    def own_context(actor: Principal, session: Database, settings: Config) -> AuthenticationContext:
        lock_and_reauthenticate(session, actor, actor.user_id, settings)
        context = authenticated_context(actor.credentials, session, settings)
        if context.family is None:
            raise HTTPException(403, "A server-side session is required")
        return context

    @router.post("/mfa/enroll", response_model=EnrollmentIssued)
    def enroll(
        payload: Reauthentication, actor: Limited, session: Database, settings: Config
    ) -> EnrollmentIssued:
        def operation() -> EnrollmentIssued:
            context = own_context(actor, session, settings)
            if context.family is None:
                raise HTTPException(403, "A server-side session is required")
            return mfa.enroll(
                session, context.user, context.family, payload.password.get_secret_value(), settings
            )

        return execute(session, operation)

    @router.post("/mfa/confirm", response_model=RecoveryIssued)
    def confirm(
        payload: MFAProof, actor: Limited, session: Database, settings: Config
    ) -> RecoveryIssued:
        def operation() -> RecoveryIssued:
            context = own_context(actor, session, settings)
            if context.family is None:
                raise HTTPException(403, "A server-side session is required")
            return mfa.confirm(
                session,
                context.user,
                context.family,
                payload.password.get_secret_value(),
                payload.code.get_secret_value(),
                settings,
            )

        return execute(session, operation)

    @router.post("/mfa/verify", status_code=204)
    def verify(payload: MFAProof, actor: Limited, session: Database, settings: Config) -> Response:
        def operation() -> None:
            context = own_context(actor, session, settings)
            if context.family is None:
                raise HTTPException(403, "A server-side session is required")
            mfa.verify(
                session,
                context.user,
                context.family,
                payload.password.get_secret_value(),
                payload.code.get_secret_value(),
                settings,
            )

        execute(session, operation)
        return Response(status_code=204)

    @router.post("/mfa/disable", status_code=204)
    def disable(payload: MFAProof, actor: Limited, session: Database, settings: Config) -> Response:
        def operation() -> None:
            context = own_context(actor, session, settings)
            mfa.ensure_factor_removable(session, actor.user_id)
            mfa.consume_proof(
                session,
                context.user,
                payload.password.get_secret_value(),
                payload.code.get_secret_value(),
                settings,
            )
            mfa.retire_factor(session, actor.user_id, actor.user_id)

        execute(session, operation)
        return Response(status_code=204)

    @router.post("/users/{user_id}/mfa/reset", status_code=204)
    def reset(user_id: UUID, actor: Limited, session: Database, settings: Config) -> Response:
        def operation() -> None:
            context = authenticated_context(actor.credentials, session, settings)
            policy.require_privileged(
                session, context.user, "roles:assign", settings, session_id=actor.session_id
            )
            if actor.user_id == user_id:
                raise policy.forbidden(actor.user_id)
            user = lock_and_reauthenticate(session, actor, user_id, settings, roles=True)
            policy.require_privileged(
                session, user, "roles:assign", settings, session_id=actor.session_id
            )
            if session.get(User, user_id) is None:
                raise HTTPException(404, "Resource not found")
            mfa.retire_factor(session, user_id, actor.user_id)

        execute(session, operation)
        return Response(status_code=204)

    return router


router = make_router("/api/v1/auth", bearer_principal, browser=False)
browser_router = make_router("/api/v1/auth/browser", browser_principal, browser=True)
