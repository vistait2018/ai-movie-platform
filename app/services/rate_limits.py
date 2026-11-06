import logging
from functools import lru_cache
from hashlib import sha256
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from redis import Redis
from redis.exceptions import RedisError

from app.core.settings import Settings, get_settings
from app.schemas.auth import (
    ActionConfirmation,
    EmailActionRequest,
    LoginRequest,
    PasswordResetConfirmation,
)

_COUNTER = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


@lru_cache
def get_registration_redis() -> Redis:
    secret = get_settings().redis_url
    if secret is None:
        raise RuntimeError("Redis configuration required")
    return Redis.from_url(secret.get_secret_value(), socket_connect_timeout=2, socket_timeout=2)


def limit_registration(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> None:
    address = request.client.host if request.client else "unknown"
    key = "auth:registration:" + sha256(address.encode()).hexdigest()
    try:
        client = get_registration_redis()
        result = client.eval(_COUNTER, 1, key, str(settings.registration_window_seconds))
        if not isinstance(result, int):
            raise RuntimeError("Unexpected rate limit response")
        count = result
    except (RedisError, RuntimeError):
        raise HTTPException(
            status_code=503, detail="Registration temporarily unavailable"
        ) from None
    if count > settings.registration_requests_per_window:
        raise HTTPException(
            status_code=429,
            detail="Too many registration requests",
            headers={"Retry-After": str(settings.registration_window_seconds)},
        )


def limit_login(
    payload: LoginRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    address = request.client.host if request.client else "unknown"
    try:
        client = get_registration_redis()
        # Separate IP and account limits: distributed guessing and IP account spraying are bounded.
        for kind, value in (("ip", address), ("account", str(payload.email))):
            key = "auth:login:" + kind + ":" + sha256(value.encode()).hexdigest()
            count = client.eval(_COUNTER, 1, key, str(settings.login_window_seconds))
            if not isinstance(count, int):
                raise RuntimeError("Unexpected rate limit response")
            if count > settings.login_requests_per_window:
                import logging

                logging.getLogger("movie.auth").info("login_rate_limited")
                raise HTTPException(
                    429,
                    "Too many login requests",
                    headers={"Retry-After": str(settings.login_window_seconds)},
                )
    except (RedisError, RuntimeError):
        raise HTTPException(503, "Authentication temporarily unavailable") from None


def check_action_limits(request: Request, identity: str, settings: Settings, limit: int) -> None:
    address = request.client.host if request.client else "unknown"
    scope = sha256(request.url.path.encode()).hexdigest()
    try:
        client = get_registration_redis()
        for kind, value in (("ip", address), ("identity", identity)):
            key = "auth:action:" + scope + ":" + kind + ":" + sha256(value.encode()).hexdigest()
            count = client.eval(_COUNTER, 1, key, str(settings.action_window_seconds))
            if not isinstance(count, int):
                raise RuntimeError("Unexpected rate limit response")
            if count > limit:
                logging.getLogger("movie.auth").info("identity_action_rate_limited")
                raise HTTPException(
                    429,
                    "Too many authentication requests",
                    headers={"Retry-After": str(settings.action_window_seconds)},
                )
    except (RedisError, RuntimeError):
        logging.getLogger("movie.auth").warning("identity_action_rate_unavailable")
        raise HTTPException(503, "Authentication temporarily unavailable") from None


def limit_action_request(
    payload: EmailActionRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    check_action_limits(request, str(payload.email), settings, settings.action_requests_per_window)


def limit_action_confirmation(
    payload: ActionConfirmation,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    check_action_limits(
        request,
        payload.token.get_secret_value(),
        settings,
        settings.action_confirmations_per_window,
    )


def limit_reset_confirmation(
    payload: PasswordResetConfirmation,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    check_action_limits(
        request,
        payload.token.get_secret_value(),
        settings,
        settings.action_confirmations_per_window,
    )
