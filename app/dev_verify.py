"""Explicit local fixture preparation, never a production email-verification endpoint."""

import argparse
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.db.session import get_engine
from app.models.identity import SecurityEvent, User


def verify_local_user(session: Session, email: str, settings: Settings, *, confirmed: bool) -> None:
    if not confirmed or settings.environment not in {"development", "test"}:
        raise ValueError("Local development confirmation required")
    database = settings.database_url
    if database is None or urlsplit(database.get_secret_value()).hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
        "postgres",
    }:
        raise ValueError("Explicitly local database required")
    with session.begin():
        user = session.scalar(
            select(User).where(User.email == email.strip().casefold()).with_for_update()
        )
        if user is None or user.status != "pending":
            raise ValueError("An existing pending local account is required")
        user.email_verified_at = datetime.now(UTC)
        user.status = "active"
        session.add(SecurityEvent(subject_user_id=user.id, event="development_email_verified"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--confirm-local-development", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    # Refuse non-development execution before even opening a database connection.
    if settings.environment != "development" or not args.confirm_local_development:
        parser.error("Only explicitly confirmed development use is allowed")
    try:
        with Session(get_engine()) as session:
            verify_local_user(session, args.email, settings, confirmed=True)
    except Exception:
        print("Local verification refused or unavailable; no sensitive details displayed.")
        return 1
    print("Local fixture verified; production verification is not implemented by this command.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
