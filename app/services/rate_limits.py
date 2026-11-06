from functools import lru_cache
from hashlib import sha256
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from redis import Redis
from redis.exceptions import RedisError

from app.core.settings import Settings, get_settings

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
