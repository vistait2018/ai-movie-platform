"""Shared identity authorization routes for separate bearer/cookie adapters."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.browser import browser_credentials, browser_guard
from app.api.dependencies import bearer, current_user
from app.core.settings import Settings, get_settings
from app.db.session import DatabaseUnavailable, get_db_session
from app.models.identity import Role, SecurityEvent, User, UserRole
from app.schemas.auth import CurrentUser
from app.schemas.users import ProfileUpdate
from app.services import authorization as policy
from app.services.rate_limits import limit_authorization
from app.services.sessions import active_user, revoke_user_sessions

logger = logging.getLogger("movie.authorization")
Database = Annotated[Session, Depends(get_db_session)]
Config = Annotated[Settings, Depends(get_settings)]


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    credentials: HTTPAuthorizationCredentials = field(repr=False)


def bearer_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Database,
    settings: Config,
) -> Principal:
    if credentials is None:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    user = current_user(credentials, session, settings)
    return Principal(user.id, credentials)


def browser_principal(request: Request, session: Database, settings: Config) -> Principal:
    credentials = browser_credentials(request, settings)
    user = current_user(credentials, session, settings)
    return Principal(user.id, credentials)


def permission_dependency(permission: str) -> Callable[..., User]:
    def check(user: Annotated[User, Depends(current_user)], session: Database) -> User:
        try:
            policy.require_permission(session, user, permission)
        except SQLAlchemyError:
            raise HTTPException(503, "Authorization temporarily unavailable") from None
        return user

    return check


def execute[T](session: Session, operation: Callable[[], T]) -> T:
    try:
        return operation()
    except (SQLAlchemyError, DatabaseUnavailable):
        session.rollback()
        logger.warning("authorization_unavailable")
        raise HTTPException(503, "Authorization temporarily unavailable") from None
    except HTTPException:
        session.rollback()
        raise


def lock_and_reauthenticate(
    session: Session,
    principal: Principal,
    target_id: UUID,
    settings: Settings,
    *,
    roles: bool = False,
) -> User:
    if roles:
        # Stable application namespace; serializes role changes and last-admin decisions.
        session.execute(text("SELECT pg_advisory_xact_lock(724019312)"))
    session.scalars(
        select(User)
        .where(User.id.in_({principal.user_id, target_id}))
        .order_by(User.id)
        .with_for_update()
    ).all()
    session.expire_all()
    return current_user(principal.credentials, session, settings)


def profile(session: Session, user_id: UUID) -> CurrentUser:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Resource not found")
    return CurrentUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        roles=policy.roles_for(session, user.id),
    )


def change_role(
    session: Session,
    principal: Principal,
    target_id: UUID,
    code: str,
    settings: Settings,
    *,
    grant: bool,
) -> None:
    initial = current_user(principal.credentials, session, settings)
    policy.require_privileged(session, initial, "roles:assign", settings)
    if target_id == principal.user_id or code not in policy.ROLES:
        raise policy.forbidden(principal.user_id)
    actor = lock_and_reauthenticate(session, principal, target_id, settings, roles=True)
    policy.require_privileged(session, actor, "roles:assign", settings)
    if target_id == actor.id or code not in policy.ROLES:
        raise policy.forbidden(actor.id)
    target = session.get(User, target_id)
    if target is None:
        raise HTTPException(404, "Resource not found")
    if grant and not active_user(target):
        raise policy.forbidden(actor.id)
    role = session.scalar(select(Role).where(Role.code == code))
    if role is None:
        raise DatabaseUnavailable("Role seed unavailable")
    link = session.get(UserRole, (target_id, role.id))
    if (grant and link is not None) or (not grant and link is None):
        session.commit()
        return
    if not grant and code == "super_admin" and active_user(target):
        count = session.scalar(
            select(func.count())
            .select_from(UserRole)
            .join(User, User.id == UserRole.user_id)
            .where(
                UserRole.role_id == role.id,
                User.status == "active",
                User.email_verified_at.is_not(None),
            )
        )
        if count is None or count <= 1:
            raise HTTPException(409, "Role change conflicts with account safeguards")
    if grant:
        session.add(UserRole(user_id=target_id, role_id=role.id))
    else:
        session.execute(
            delete(UserRole).where(UserRole.user_id == target_id, UserRole.role_id == role.id)
        )
    revoke_user_sessions(session, target_id, policy.now(), "role_changed")
    event = "role_granted" if grant else "role_revoked"
    session.add(SecurityEvent(subject_user_id=target_id, event=f"{event}:{actor.id}:{code}"))
    session.commit()
    logger.info(
        event,
        extra={
            "actor_id": str(principal.user_id),
            "target_user_id": str(target_id),
            "role_code": code,
        },
    )


def make_router(
    prefix: str, authentication: Callable[..., Principal], *, browser: bool
) -> APIRouter:
    router = APIRouter(
        prefix=prefix,
        tags=["User authorization"],
        dependencies=[Depends(browser_guard)] if browser else [],
        responses={
            401: {"description": "Authentication required"},
            403: {"description": "Access denied"},
            503: {"description": "Authorization unavailable"},
        },
    )
    Actor = Annotated[Principal, Depends(authentication)]

    @router.get("/users/{user_id}", response_model=CurrentUser)
    def read_profile(
        user_id: UUID, actor: Actor, session: Database, settings: Config
    ) -> CurrentUser:
        def read() -> CurrentUser:
            user = current_user(actor.credentials, session, settings)
            policy.require_owner(session, user, user_id, action="read", settings=settings)
            logger.info(
                "profile_read",
                extra={"actor_id": str(actor.user_id), "target_user_id": str(user_id)},
            )
            return profile(session, user_id)

        return execute(session, read)

    @router.patch(
        "/users/{user_id}", response_model=CurrentUser, dependencies=[Depends(limit_authorization)]
    )
    def update_profile(
        user_id: UUID, payload: ProfileUpdate, actor: Actor, session: Database, settings: Config
    ) -> CurrentUser:
        def update() -> CurrentUser:
            initial = current_user(actor.credentials, session, settings)
            policy.require_owner(session, initial, user_id, action="update", settings=settings)
            user = lock_and_reauthenticate(session, actor, user_id, settings)
            policy.require_owner(session, user, user_id, action="update", settings=settings)
            target = session.get(User, user_id)
            if target is None:
                raise HTTPException(404, "Resource not found")
            target.display_name = payload.display_name
            session.add(
                SecurityEvent(subject_user_id=user_id, event=f"profile_updated:{actor.user_id}")
            )
            session.flush()
            result = profile(session, user_id)
            session.commit()
            return result

        return execute(session, update)

    @router.get("/users/{user_id}/roles")
    def read_roles(
        user_id: UUID, actor: Actor, session: Database, settings: Config
    ) -> dict[str, list[str]]:
        def read() -> dict[str, list[str]]:
            user = current_user(actor.credentials, session, settings)
            policy.require_owner(session, user, user_id, action="read", settings=settings)
            if session.get(User, user_id) is None:
                raise HTTPException(404, "Resource not found")
            return {"roles": policy.roles_for(session, user_id)}

        return execute(session, read)

    @router.get("/authorization/roles")
    def catalogue(actor: Actor, session: Database, settings: Config) -> dict[str, list[str]]:
        def read() -> dict[str, list[str]]:
            user = current_user(actor.credentials, session, settings)
            policy.require_privileged(session, user, "roles:assign", settings)
            return {"roles": sorted(policy.ROLES)}

        return execute(session, read)

    @router.put(
        "/users/{user_id}/roles/{role_code}",
        status_code=204,
        dependencies=[Depends(limit_authorization)],
    )
    def grant_role(
        user_id: UUID, role_code: str, actor: Actor, session: Database, settings: Config
    ) -> Response:
        execute(
            session, lambda: change_role(session, actor, user_id, role_code, settings, grant=True)
        )
        return Response(status_code=204)

    @router.delete(
        "/users/{user_id}/roles/{role_code}",
        status_code=204,
        dependencies=[Depends(limit_authorization)],
    )
    def revoke_role(
        user_id: UUID, role_code: str, actor: Actor, session: Database, settings: Config
    ) -> Response:
        execute(
            session, lambda: change_role(session, actor, user_id, role_code, settings, grant=False)
        )
        return Response(status_code=204)

    return router


router = make_router("/api/v1", bearer_principal, browser=False)
browser_router = make_router("/api/v1/auth/browser", browser_principal, browser=True)
