from celery import Celery
from celery.signals import setup_logging

from app.core.logging import configure_logging
from app.core.settings import get_settings

settings = get_settings()
celery_app = Celery("movie")
if settings.redis_url is None:
    raise RuntimeError("APP_REDIS_URL is required to start the worker")
celery_app.conf.broker_url = settings.redis_url.get_secret_value()
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=240,
    task_time_limit=300,
    timezone="UTC",
    enable_utc=True,
)


@setup_logging.connect
def worker_logging(**kwargs: object) -> None:
    configure_logging(settings.log_level)


@celery_app.task(name="movie.ping")
def ping() -> dict[str, str]:
    return {"status": "ok"}
