"""Strict first-party access JWTs. No refresh credentials or client secrets."""

from datetime import datetime
from uuid import UUID

import jwt

from app.core.settings import Settings


class TokenConfigurationError(RuntimeError):
    pass


def signing_key(settings: Settings) -> str:
    secret = settings.access_signing_key
    value = secret.get_secret_value() if secret else ""
    if len(value.encode()) < 32 or value.startswith("replace-"):
        raise TokenConfigurationError("A generated access signing key is required")
    return value


def encode_access(
    user_id: UUID, grant_id: UUID, issued: datetime, expires: datetime, settings: Settings
) -> str:
    return jwt.encode(
        {
            "sub": str(user_id),
            "jti": str(grant_id),
            "iat": int(issued.timestamp()),
            "nbf": int(issued.timestamp()),
            "exp": int(expires.timestamp()),
            "iss": settings.access_token_issuer,
            "aud": settings.access_token_audience,
            "purpose": "access",
        },
        signing_key(settings),
        algorithm="HS256",
        headers={"typ": "at+jwt"},
    )


def decode_access(token: str, settings: Settings) -> tuple[UUID, UUID, int]:
    key = signing_key(settings)
    if len(token) > 4096:
        raise jwt.InvalidTokenError("Invalid access token")
    claims = jwt.decode(
        token,
        key,
        algorithms=["HS256"],
        issuer=settings.access_token_issuer,
        audience=settings.access_token_audience,
        options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub", "jti"], "strict_aud": True},
    )
    if jwt.get_unverified_header(token).get("typ") != "at+jwt":
        raise jwt.InvalidTokenError("Invalid token type")
    if claims.get("purpose") != "access":
        raise jwt.InvalidTokenError("Invalid token use")
    for name in ("iat", "nbf", "exp"):
        if type(claims[name]) is not int:
            raise jwt.InvalidTokenError("Invalid timestamp")
    if not 0 < claims["exp"] - claims["iat"] <= settings.access_token_seconds:
        raise jwt.InvalidTokenError("Invalid lifetime")
    if claims["nbf"] != claims["iat"]:
        raise jwt.InvalidTokenError("Invalid validity window")
    try:
        user_id, grant_id = UUID(claims["sub"]), UUID(claims["jti"])
        if str(user_id) != claims["sub"] or str(grant_id) != claims["jti"]:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise jwt.InvalidTokenError("Invalid subject or identifier") from None
    return user_id, grant_id, claims["exp"]
