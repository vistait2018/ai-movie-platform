"""Browser transport and session-bound CSRF; never log cookie/header values."""

import hmac
import logging
from datetime import UTC, datetime
from hashlib import sha256
from secrets import token_urlsafe
from urllib.parse import urlsplit

import jwt
from fastapi import HTTPException, Request, Response

from app.core.settings import Settings
from app.core.tokens import signing_key

PATH = "/api/v1/auth/browser"
logger = logging.getLogger("movie.auth")


def cookie_name(kind: str, settings: Settings) -> str:
    return ("__Secure-" if settings.browser_cookie_secure else "") + "movie_" + kind


def read_cookie(request: Request, kind: str, settings: Settings) -> str:
    name = cookie_name(kind, settings)
    # Reject duplicate cookie names instead of accepting parser-dependent shadowing.
    values = [
        part.strip().split("=", 1)
        for part in request.headers.get("cookie", "").split(";")
        if "=" in part
    ]
    if sum(key == name for key, _ in values) > 1:
        raise HTTPException(401, "Authentication required")
    value = request.cookies.get(name, "")
    if len(value) > 4096:
        raise HTTPException(401, "Authentication required")
    return value


def set_cookie(response: Response, kind: str, value: str, seconds: int, settings: Settings) -> None:
    response.set_cookie(
        cookie_name(kind, settings),
        value,
        max_age=min(seconds, settings.browser_cookie_seconds),
        path=PATH,
        secure=settings.browser_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_cookies(response: Response, settings: Settings) -> None:
    for kind in ("access", "refresh", "bootstrap"):
        response.delete_cookie(
            cookie_name(kind, settings),
            path=PATH,
            secure=settings.browser_cookie_secure,
            httponly=True,
            samesite="lax",
        )


def binding(request: Request, settings: Settings) -> str:
    refresh = read_cookie(request, "refresh", settings)
    bootstrap = read_cookie(request, "bootstrap", settings)
    value = "refresh:" + refresh if refresh else "bootstrap:" + bootstrap if bootstrap else ""
    return sha256(value.encode()).hexdigest() if value else ""


def csrf_key(settings: Settings) -> bytes:
    return hmac.digest(signing_key(settings).encode(), b"browser-csrf-v1", "sha256")


def issue_csrf(bound: str, settings: Settings) -> str:
    now = int(datetime.now(UTC).timestamp())
    return jwt.encode(
        {
            "bind": bound,
            "nonce": token_urlsafe(32),
            "iat": now,
            "exp": now + settings.browser_csrf_seconds,
            "aud": "browser-csrf",
            "iss": settings.access_token_issuer,
            "purpose": "csrf",
        },
        csrf_key(settings),
        algorithm="HS256",
        headers={"typ": "csrf+jwt"},
    )


def trusted_origin(request: Request, settings: Settings) -> bool:
    origin = request.headers.get("origin")
    if origin is None:
        referer = request.headers.get("referer", "")
        try:
            parsed = urlsplit(referer)
            if parsed.username or parsed.password:
                return False
            origin = f"{parsed.scheme}://{parsed.netloc}"
        except ValueError:
            return False
    return origin in settings.browser_origins


def validate_csrf(request: Request, settings: Settings) -> None:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    token = request.headers.get("x-csrf-token", "")
    try:
        if (
            not trusted_origin(request, settings)
            or request.headers.get("content-type", "").split(";")[0].strip() != "application/json"
            or not token
            or len(token) > 2048
        ):
            raise jwt.InvalidTokenError()
        claims = jwt.decode(
            token,
            csrf_key(settings),
            algorithms=["HS256"],
            audience="browser-csrf",
            issuer=settings.access_token_issuer,
            options={"require": ["exp", "iat", "bind", "nonce", "purpose"], "strict_aud": True},
        )
        bound = binding(request, settings)
        if (
            jwt.get_unverified_header(token).get("typ") != "csrf+jwt"
            or claims["purpose"] != "csrf"
            or not bound
            or not isinstance(claims["bind"], str)
            or not hmac.compare_digest(bound, claims["bind"])
            or type(claims["iat"]) is not int
            or type(claims["exp"]) is not int
            or not 0 < claims["exp"] - claims["iat"] <= settings.browser_csrf_seconds
        ):
            raise jwt.InvalidTokenError()
    except jwt.InvalidTokenError:
        logger.info("browser_csrf_rejected")
        raise HTTPException(403, "Browser request rejected") from None
