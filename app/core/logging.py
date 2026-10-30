import json
import logging
import sys
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for name in ("request_id", "status_code", "duration_ms", "dependency", "error_type"):
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        return json.dumps(payload)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("movie")
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
