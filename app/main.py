import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.identity_actions import router as action_router
from app.core.logging import configure_logging
from app.core.settings import Settings, get_settings
from app.db.session import DatabaseUnavailable
from app.services.readiness import check_readiness

logger = logging.getLogger("movie.api")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    configure_logging(get_settings().log_level)
    logger.info("application_started")
    yield
    logger.info("application_stopped")


app = FastAPI(
    title="AI Movie Streaming & Creator Platform",
    description="Backend API for our AI-powered movie platform.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/")
def home() -> dict[str, str]:
    return {
        "message": "AI Movie Platform API is running!",
        "status": "success",
    }


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/live")
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/ready")
async def readiness(settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    checks = await check_readiness(settings)
    ready = all(value == "healthy" for value in checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )


@app.middleware("http")
async def request_logging(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = str(uuid4())
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            "request_failed", extra={"request_id": request_id, "error_type": type(exc).__name__}
        )
        response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_completed",
        extra={
            "request_id": request_id,
            "status_code": response.status_code,
            "duration_ms": round((perf_counter() - started) * 1000, 2),
        },
    )
    return response


app.include_router(auth_router)
app.include_router(action_router)


@app.exception_handler(RequestValidationError)
async def sanitized_validation(request: Request, error: RequestValidationError) -> JSONResponse:
    # Pydantic's default error input can include passwords; omit it and context entirely.
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"loc": item["loc"], "msg": item["msg"], "type": item["type"]}
                for item in error.errors()
            ]
        },
    )


@app.exception_handler(DatabaseUnavailable)
async def unavailable_database(request: Request, error: DatabaseUnavailable) -> JSONResponse:
    logger.warning("registration_unavailable", extra={"error_type": type(error).__name__})
    return JSONResponse(status_code=503, content={"detail": "Registration temporarily unavailable"})
