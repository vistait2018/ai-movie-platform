"""Verified STARTTLS transport. SMTP submission is not proof of sandbox capture."""

import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from uuid import UUID

from app.core.settings import Settings
from app.services.email_delivery import DeliveryUnavailable


def validate_smtp(settings: Settings) -> None:
    host = (settings.smtp_host or "").lower().rstrip(".")
    sandbox = host in {"sandbox.smtp.mailtrap.io", "smtp.mailtrap.io"}
    if settings.email_provider not in {"mailtrap_sandbox", "smtp"}:
        raise DeliveryUnavailable("SMTP delivery is not configured")
    if settings.environment == "production" and (
        sandbox or settings.email_provider == "mailtrap_sandbox"
    ):
        raise DeliveryUnavailable("Sandbox delivery is forbidden in production")
    if settings.email_provider == "mailtrap_sandbox" and host != "sandbox.smtp.mailtrap.io":
        raise DeliveryUnavailable("Mailtrap sandbox host required")
    if (
        not settings.smtp_starttls
        or not re.fullmatch(r"[a-zA-Z0-9.-]+", host)
        or settings.email_from_address is None
        or any(c in settings.email_from_name for c in "\r\n")
    ):
        raise DeliveryUnavailable("Secure SMTP configuration required")
    for secret in (settings.smtp_username, settings.smtp_password):
        if (
            secret is None
            or not secret.get_secret_value()
            or secret.get_secret_value().startswith("replace-")
        ):
            raise DeliveryUnavailable("SMTP credentials required")


def render_email(message: dict[str, str], delivery_id: UUID, settings: Settings) -> EmailMessage:
    result = EmailMessage()
    result["From"] = formataddr((settings.email_from_name, str(settings.email_from_address)))
    result["To"] = message["recipient"]
    result["Message-ID"] = f"<{delivery_id}@ai-movie-platform.local>"
    result["Subject"] = (
        "AI Movie Platform — Verify your email"
        if message["purpose"] == "verify_email"
        else "AI Movie Platform — Reset your password"
    )
    result.set_content(
        "Use this single-use token in the AI Movie Platform confirmation form.\n\n"
        + "Token: "
        + message["token"]
        + "\n"
        + "Expires (UTC): "
        + message["expires_at"]
        + "\n"
        + "Confirmation endpoint: "
        + message["confirmation_endpoint"]
        + "\n\n"
        + "If you did not request this, ignore this message. Never share this token.\n"
    )
    return result


class SMTPTransport:
    def __init__(self, settings: Settings):
        validate_smtp(settings)
        self.settings = settings

    def send(self, message: dict[str, str], delivery_id: UUID) -> None:
        settings = self.settings
        validate_smtp(settings)
        if (
            settings.smtp_username is None
            or settings.smtp_password is None
            or settings.smtp_host is None
        ):
            raise DeliveryUnavailable("Secure SMTP configuration required")
        try:
            with smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
            ) as client:
                client.ehlo()
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
                client.login(
                    settings.smtp_username.get_secret_value(),
                    settings.smtp_password.get_secret_value(),
                )
                refused = client.send_message(render_email(message, delivery_id, settings))
                if refused:
                    raise DeliveryUnavailable("SMTP submission unavailable")
        except (smtplib.SMTPException, OSError, ValueError):
            # Do not expose provider replies, recipient addresses, authentication data or body.
            raise DeliveryUnavailable("SMTP submission unavailable") from None
