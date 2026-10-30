import asyncio
import logging
import math

import psycopg
from redis.asyncio import Redis

from app.core.settings import Settings

logger = logging.getLogger("movie.readiness")


def _ping_database(url: str, timeout: float) -> None:
    # Threaded psycopg works with Windows Proactor and Linux event loops alike.
    with psycopg.connect(
        url,
        connect_timeout=math.ceil(timeout),
        options=f"-c statement_timeout={math.ceil(timeout * 1000)}",
        autocommit=True,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone() != (1,):
                raise RuntimeError("Unexpected database response")


async def ping_database(url: str, timeout: float) -> None:
    await asyncio.to_thread(_ping_database, url, timeout)


async def ping_redis(url: str, timeout: float) -> None:
    client = Redis.from_url(url, socket_connect_timeout=timeout, socket_timeout=timeout)
    try:
        if not await client.ping():
            raise RuntimeError("Unexpected Redis response")
    finally:
        await client.aclose()


async def check_readiness(settings: Settings) -> dict[str, str]:
    async def check(name: str) -> tuple[str, str]:
        secret = settings.database_url if name == "database" else settings.redis_url
        if secret is None:
            return name, "unconfigured"
        try:
            async with asyncio.timeout(settings.readiness_timeout_seconds):
                probe = ping_database if name == "database" else ping_redis
                await probe(secret.get_secret_value(), settings.readiness_timeout_seconds)
            return name, "healthy"
        except Exception as exc:
            logger.warning(
                "dependency_unavailable",
                extra={"dependency": name, "error_type": type(exc).__name__},
            )
            return name, "unavailable"

    return dict(await asyncio.gather(check("database"), check("redis")))
