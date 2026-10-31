from alembic import context

from app.core.settings import get_settings
from app.db.base import Base
from app.db.session import build_engine
from app.models import identity  # noqa: F401 - register model metadata

config = context.config
target_metadata = Base.metadata


def run_with_connection(connection):
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError(
        "Use an online migration connection; no credentials are written to alembic.ini"
    )
else:
    supplied = config.attributes.get("connection")
    if supplied is not None:
        run_with_connection(supplied)
    else:
        secret = get_settings().database_url
        if secret is None:
            raise RuntimeError("APP_DATABASE_URL is required")
        engine = build_engine(secret.get_secret_value())
        try:
            with engine.connect() as connection:
                run_with_connection(connection)
        finally:
            engine.dispose()
