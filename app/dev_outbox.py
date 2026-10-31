"""Export selected local development email messages without printing credentials."""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.db.session import get_engine
from app.models.identity import AuthAction, EmailOutbox
from app.services.email_delivery import outbox_cipher


def local_messages(
    session: Session, email: str, settings: Settings, *, confirmed: bool
) -> list[dict[str, str]]:
    if not confirmed or settings.environment not in {"development", "test"}:
        raise ValueError("Explicit local development access required")
    database = settings.database_url
    if database is None or urlsplit(database.get_secret_value()).hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
        "postgres",
    }:
        raise ValueError("Local database required")
    cipher = outbox_cipher(settings)
    encrypted = session.scalars(
        select(EmailOutbox.encrypted_payload)
        .join(AuthAction, EmailOutbox.action_id == AuthAction.id)
        .where(
            AuthAction.recipient == email.strip().casefold(),
            AuthAction.consumed_at.is_(None),
            AuthAction.expires_at > datetime.now(UTC),
        )
        .order_by(EmailOutbox.created_at.desc())
        .limit(10)
    ).all()
    messages = []
    for value in encrypted:
        message = json.loads(cipher.decrypt(value))
        if not isinstance(message, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in message.items()
        ):
            raise ValueError("Invalid outbox message")
        messages.append(message)
    return messages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--confirm-local-development", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if settings.environment != "development" or not args.confirm_local_development:
        parser.error("Only explicitly confirmed development access is allowed")
    try:
        with Session(get_engine()) as session:
            messages = local_messages(session, args.email, settings, confirmed=True)
        if not messages:
            print("No current messages for the selected local account.")
            return 0
        directory = Path(".tools/outbox")
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (uuid4().hex + ".json")
        # Exclusive file creation; Unix owner-only mode. Windows inherits the local user's ACL.
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(messages, output, indent=2)
        print("Sensitive local messages exported to " + str(target.resolve()))
        print("Inspect locally, never share/commit, and delete this export after use.")
    except Exception:
        print("Outbox access refused or unavailable; no sensitive details displayed.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
