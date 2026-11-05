"""Durable metadata jobs; raw SMTP action credentials exist only in worker memory."""

import logging
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from typing import Protocol
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.models.identity import AuthAction, SecurityEvent, SMTPDelivery, User
from app.services.email_delivery import DeliveryUnavailable
from app.services.identity_actions import ActionKind, digest_action, eligible
from app.services.smtp_transport import SMTPTransport, validate_smtp

logger = logging.getLogger("movie.email")


class MailTransport(Protocol):
    def send(self, message: dict[str, str], delivery_id: UUID) -> None: ...


def prepare_delivery(
    engine: Engine, delivery_id: UUID, settings: Settings
) -> tuple[int, dict[str, str]] | None:
    with Session(engine) as session, session.begin():
        reference = session.execute(
            select(AuthAction.id, AuthAction.user_id)
            .join(SMTPDelivery, SMTPDelivery.action_id == AuthAction.id)
            .where(SMTPDelivery.id == delivery_id)
        ).one_or_none()
        if reference is None:
            return None
        user = session.scalar(
            select(User).where(User.id == reference.user_id).with_for_update(skip_locked=True)
        )
        if user is None:
            return None
        action = session.scalar(
            select(AuthAction).where(AuthAction.id == reference.id).with_for_update()
        )
        delivery = session.scalar(
            select(SMTPDelivery).where(SMTPDelivery.id == delivery_id).with_for_update()
        )
        now = datetime.now(UTC)
        if (
            action is None
            or delivery is None
            or delivery.provider != settings.email_provider
            or delivery.status not in {"pending", "sending"}
            or delivery.next_attempt_at > now
            or (delivery.leased_until is not None and delivery.leased_until > now)
        ):
            return None
        kind: ActionKind = "verify_email" if action.kind == "verify_email" else "reset_password"
        if (
            action.consumed_at is not None
            or action.expires_at <= now
            or action.recipient != user.email
            or not eligible(user, kind)
        ):
            delivery.status = "cancelled"
            delivery.last_error_code = "action_ineligible"
            return None
        if delivery.attempts >= 5:
            delivery.status = "failed"
            delivery.last_error_code = "attempt_limit"
            return None
        value = token_urlsafe(32)
        action.token_digest = digest_action(kind, value)
        delivery.attempts += 1
        delivery.status = "sending"
        delivery.leased_until = now + timedelta(seconds=settings.smtp_timeout_seconds * 12 + 60)
        message = {
            "recipient": action.recipient,
            "purpose": kind,
            "token": value,
            "expires_at": action.expires_at.isoformat(),
            "confirmation_endpoint": "/api/v1/auth/verify-email"
            if kind == "verify_email"
            else "/api/v1/auth/reset-password",
        }
        return delivery.attempts, message
    # The context commits before the caller can perform any SMTP I/O.


def finish_delivery(engine: Engine, delivery_id: UUID, attempt: int, *, submitted: bool) -> None:
    with Session(engine) as session, session.begin():
        reference = session.execute(
            select(AuthAction.user_id)
            .join(SMTPDelivery, SMTPDelivery.action_id == AuthAction.id)
            .where(SMTPDelivery.id == delivery_id)
        ).one_or_none()
        if reference is None:
            return
        session.scalar(select(User).where(User.id == reference.user_id).with_for_update())
        delivery = session.scalar(
            select(SMTPDelivery).where(SMTPDelivery.id == delivery_id).with_for_update()
        )
        if delivery is None or delivery.attempts != attempt or delivery.status != "sending":
            return
        now = datetime.now(UTC)
        delivery.leased_until = None
        if submitted:
            delivery.status = "submitted"
            delivery.submitted_at = now
            delivery.last_error_code = None
        else:
            delivery.status = "pending" if attempt < 5 else "failed"
            delivery.next_attempt_at = now + timedelta(seconds=min(30 * 2**attempt, 600))
            delivery.last_error_code = "smtp_unavailable"
        action = session.get(AuthAction, delivery.action_id)
        session.add(
            SecurityEvent(
                subject_user_id=action.user_id if action else None,
                event="email_smtp_submitted" if submitted else "email_smtp_failed",
            )
        )


def dispatch_due_emails(
    engine: Engine, settings: Settings, transport: MailTransport | None = None, *, limit: int = 10
) -> dict[str, int]:
    result = {"submitted": 0, "failed": 0}
    if settings.email_provider == "outbox":
        return result
    validate_smtp(settings)
    sender = transport or SMTPTransport(settings)
    now = datetime.now(UTC)
    with Session(engine) as session:
        candidates = session.scalars(
            select(SMTPDelivery.id)
            .where(
                SMTPDelivery.provider == settings.email_provider,
                SMTPDelivery.status.in_(["pending", "sending"]),
                SMTPDelivery.next_attempt_at <= now,
                or_(SMTPDelivery.leased_until.is_(None), SMTPDelivery.leased_until <= now),
            )
            .order_by(SMTPDelivery.next_attempt_at)
            .limit(min(max(limit, 1), 50))
        ).all()
    for delivery_id in candidates:
        prepared = prepare_delivery(engine, delivery_id, settings)
        if prepared is None:
            continue
        attempt, message = prepared
        try:
            sender.send(message, delivery_id)
        except DeliveryUnavailable:
            finish_delivery(engine, delivery_id, attempt, submitted=False)
            logger.warning("email_smtp_unavailable")
            result["failed"] += 1
        else:
            finish_delivery(engine, delivery_id, attempt, submitted=True)
            logger.info("email_smtp_submitted")
            result["submitted"] += 1
    return result
