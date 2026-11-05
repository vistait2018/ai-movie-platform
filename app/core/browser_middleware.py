"""Exact CORS/host boundaries and security headers, including error responses."""

from starlette.datastructures import MutableHeaders
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.settings import get_settings


class BrowserSecurityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        settings = get_settings()

        async def secured_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
                if scope["path"] not in {"/docs", "/redoc", "/docs/oauth2-redirect"}:
                    headers["Content-Security-Policy"] = (
                        "default-src 'none'; frame-ancestors 'none'"
                    )
                if scope["path"].startswith(
                    ("/api/v1/auth", "/api/v1/users", "/api/v1/authorization")
                ):
                    headers["Cache-Control"] = "no-store"
                    headers["Pragma"] = "no-cache"
                if settings.environment in {"staging", "production"}:
                    headers["Strict-Transport-Security"] = "max-age=31536000"
            await send(message)

        cors = CORSMiddleware(
            self.app,
            allow_origins=settings.browser_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "X-CSRF-Token", "Authorization"],
            max_age=600,
        )
        # Validate Host even for preflight, which CORS handles without calling its inner app.
        guarded = TrustedHostMiddleware(
            cors, allowed_hosts=settings.trusted_hosts, www_redirect=False
        )
        await guarded(scope, receive, secured_send)
