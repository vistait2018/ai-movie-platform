"""Transaction-bound delivery interface. No external provider or public outbox API."""

import json
from typing import Protocol
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.models.identity import EmailOutbox


class DeliveryUnavailable(RuntimeError):
    pass


class EmailDelivery(Protocol):
    def enqueue(self, session: Session, action_id: UUID, message: dict[str, str]) -> None: ...


def outbox_cipher(settings: Settings) -> Fernet:
    if settings.environment not in {"development", "test"} or settings.email_outbox_key is None:
        raise DeliveryUnavailable("Development delivery is unavailable")
    try:
        return Fernet(settings.email_outbox_key.get_secret_value().encode("ascii"))
    except (ValueError, UnicodeError):
        raise DeliveryUnavailable("Development delivery is unavailable") from None


class DevelopmentOutbox:
    def __init__(self, settings: Settings):
        self.cipher = outbox_cipher(settings)

    def enqueue(self, session: Session, action_id: UUID, message: dict[str, str]) -> None:
        encrypted = self.cipher.encrypt(json.dumps(message).encode())
        session.add(EmailOutbox(action_id=action_id, encrypted_payload=encrypted))


def get_delivery(settings: Settings) -> EmailDelivery:
    # Future provider adapters enqueue durable jobs in this same database transaction.
    # No network send occurs before commit; staging/production fail closed until configured.
    return DevelopmentOutbox(settings)
