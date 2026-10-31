from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from app.core.settings import get_settings


class DatabaseUnavailable(RuntimeError):
    pass


def sqlalchemy_url(value: str) -> URL:
    return make_url(value).set(drivername="postgresql+psycopg")


def build_engine(value: str) -> Engine:
    return create_engine(
        sqlalchemy_url(value),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=5,
        hide_parameters=True,
        connect_args={"connect_timeout": 5},
    )


@lru_cache
def get_engine() -> Engine:
    secret = get_settings().database_url
    if secret is None:
        raise DatabaseUnavailable("Database configuration required")
    return build_engine(secret.get_secret_value())


def get_db_session() -> Iterator[Session]:
    with Session(get_engine(), expire_on_commit=False) as session:
        yield session
