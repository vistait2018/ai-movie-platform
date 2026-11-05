import os
import smtplib
import ssl
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.db.session import get_db_session
from app.main import app
from app.models.identity import AuthAction, EmailOutbox, SMTPDelivery, User
from app.services.email_delivery import DeliveryUnavailable, get_delivery
from app.services.identity_actions import digest_action
from app.services.rate_limits import (
    limit_action_confirmation,
    limit_action_request,
    limit_login,
    limit_registration,
    limit_reset_confirmation,
)
from app.services.smtp_dispatch import dispatch_due_emails
from app.services.smtp_transport import SMTPTransport, validate_smtp


def smtp_settings(**updates):
    defaults = dict(
        _env_file=None,
        environment="test",
        email_provider="mailtrap_sandbox",
        smtp_host="sandbox.smtp.mailtrap.io",
        smtp_username=SecretStr(token_urlsafe(16)),
        smtp_password=SecretStr(token_urlsafe(24)),
        email_from_address="test@example.com",
    )
    return Settings(**(defaults | updates))


def mail():
    return {
        "recipient": "viewer@example.com",
        "purpose": "verify_email",
        "token": token_urlsafe(32),
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "confirmation_endpoint": "/api/v1/auth/verify-email",
    }


def test_starttls_before_auth_and_safe_message(monkeypatch, caplog):
    calls = []
    settings = smtp_settings()
    value = mail()

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            assert host == "sandbox.smtp.mailtrap.io" and port == 2525 and timeout == 10

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def ehlo(self):
            calls.append("ehlo")

        def starttls(self, *, context):
            assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
            calls.append("tls")

        def login(self, username, password):
            assert username == settings.smtp_username.get_secret_value()
            assert password == settings.smtp_password.get_secret_value()
            calls.append("login")

        def send_message(self, message):
            calls.append("send")
            assert message["To"] == value["recipient"]
            assert value["token"] in message.get_content()
            assert "Verify your email" in message["Subject"]
            return {}

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    SMTPTransport(settings).send(value, uuid4())
    assert calls == ["ehlo", "tls", "ehlo", "login", "send"]
    assert (
        value["token"] not in caplog.text
        and settings.smtp_password.get_secret_value() not in caplog.text
    )


@pytest.mark.parametrize(
    "change",
    [
        {"smtp_starttls": False},
        {"smtp_host": None},
        {"smtp_username": None},
        {"smtp_password": None},
        {"email_from_address": None},
        {"smtp_host": "send.smtp.mailtrap.io"},
        {"email_from_name": "Injected\r\nBcc: other@example.com"},
    ],
)
def test_insecure_smtp_configuration_rejected(change):
    with pytest.raises(DeliveryUnavailable):
        validate_smtp(smtp_settings(**change))


@pytest.mark.parametrize(
    "provider,host",
    [
        ("mailtrap_sandbox", "sandbox.smtp.mailtrap.io"),
        ("smtp", "sandbox.smtp.mailtrap.io"),
        ("smtp", "smtp.mailtrap.io"),
    ],
)
def test_sandbox_cannot_be_production(provider, host):
    settings = smtp_settings().model_copy(
        update={"environment": "production", "email_provider": provider, "smtp_host": host}
    )
    with pytest.raises(DeliveryUnavailable):
        get_delivery(settings)


@pytest.mark.parametrize(
    "failure",
    [
        smtplib.SMTPAuthenticationError(535, b"private provider reply"),
        smtplib.SMTPNotSupportedError("private TLS detail"),
        TimeoutError("private host"),
    ],
)
def test_transport_failure_sanitized(monkeypatch, failure):
    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(smtplib, "SMTP", fail)
    with pytest.raises(DeliveryUnavailable) as caught:
        SMTPTransport(smtp_settings()).send(mail(), uuid4())
    assert str(caught.value) == "SMTP submission unavailable"


@pytest.fixture
def smtp_client(identity_engine, service_settings):
    if os.getenv("RUN_SERVICE_TESTS") != "1":
        pytest.skip("Real PostgreSQL required")
    settings = smtp_settings(
        database_url=service_settings.database_url, access_signing_key=SecretStr(token_urlsafe(48))
    )

    def database():
        with Session(identity_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_session] = database
    for dependency in (
        limit_registration,
        limit_login,
        limit_action_request,
        limit_action_confirmation,
        limit_reset_confirmation,
    ):
        app.dependency_overrides[dependency] = lambda: None
    with TestClient(app) as client:
        yield client, settings


class CapturedTransport:
    def __init__(self, engine, *, fail=False):
        self.engine = engine
        self.messages = []
        self.fail = fail

    def send(self, message, delivery_id):
        # Separate connection proves the digest/job committed before network transport.
        with Session(self.engine) as session:
            delivery = session.get(SMTPDelivery, delivery_id)
            action = session.get(AuthAction, delivery.action_id)
            assert delivery.status == "sending"
            assert action.token_digest == digest_action(message["purpose"], message["token"])
            assert (
                session.scalar(select(EmailOutbox).where(EmailOutbox.action_id == action.id))
                is None
            )
        self.messages.append((message, delivery_id))
        if self.fail:
            raise DeliveryUnavailable("SMTP submission unavailable")


@pytest.fixture
def smtp_account(smtp_client):
    client, _ = smtp_client
    data = {
        "email": uuid4().hex + "@example.com",
        "password": token_urlsafe(30),
        "display_name": "SMTP Viewer",
    }
    assert client.post("/api/v1/auth/register", json=data).status_code == 202
    return data


def dispatch_account(engine, settings, transport, email):
    # Limit the poll to this test's newly created action/job, preserving other test records.
    with Session(engine) as session, session.begin():
        rows = session.scalars(
            select(SMTPDelivery)
            .join(AuthAction)
            .where(AuthAction.recipient != email, SMTPDelivery.status == "pending")
        ).all()
        for row in rows:
            row.next_attempt_at = datetime.now(UTC) + timedelta(hours=1)
    return dispatch_due_emails(engine, settings, transport)


@pytest.mark.integration
def test_smtp_verification_reset_end_to_end(smtp_client, smtp_account, identity_engine, caplog):
    client, settings = smtp_client
    transport = CapturedTransport(identity_engine)
    assert (
        dispatch_account(identity_engine, settings, transport, smtp_account["email"])["submitted"]
        == 1
    )
    verification = transport.messages[-1][0]["token"]
    assert client.post("/api/v1/auth/verify-email", json={"token": verification}).status_code == 200
    credentials = {"email": smtp_account["email"], "password": smtp_account["password"]}
    access = client.post("/api/v1/auth/login", json=credentials).json()["access_token"]
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + access}).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/auth/forgot-password", json={"email": smtp_account["email"]}
        ).status_code
        == 202
    )
    assert (
        dispatch_account(identity_engine, settings, transport, smtp_account["email"])["submitted"]
        == 1
    )
    reset = transport.messages[-1][0]["token"]
    password = token_urlsafe(30)
    assert (
        client.post(
            "/api/v1/auth/reset-password", json={"token": reset, "new_password": password}
        ).status_code
        == 200
    )
    assert client.post("/api/v1/auth/login", json=credentials).status_code == 401
    assert (
        client.post("/api/v1/auth/login", json=dict(credentials, password=password)).status_code
        == 200
    )
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + access}).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/reset-password", json={"token": reset, "new_password": password}
        ).status_code
        == 400
    )
    assert (
        verification not in caplog.text and reset not in caplog.text and password not in caplog.text
    )


@pytest.mark.integration
def test_smtp_retry_rotates_tokens_and_honors_lease(smtp_client, smtp_account, identity_engine):
    client, settings = smtp_client
    transport = CapturedTransport(identity_engine, fail=True)
    assert (
        dispatch_account(identity_engine, settings, transport, smtp_account["email"])["failed"] == 1
    )
    old, delivery_id = transport.messages[-1]
    assert dispatch_due_emails(identity_engine, settings, transport)["failed"] == 0
    with Session(identity_engine) as session, session.begin():
        row = session.get(SMTPDelivery, delivery_id)
        assert row.last_error_code == "smtp_unavailable" and row.attempts == 1
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    transport.fail = False
    assert dispatch_due_emails(identity_engine, settings, transport)["submitted"] == 1
    new = transport.messages[-1][0]
    assert old["token"] != new["token"]
    assert client.post("/api/v1/auth/verify-email", json={"token": old["token"]}).status_code == 400
    assert client.post("/api/v1/auth/verify-email", json={"token": new["token"]}).status_code == 200


@pytest.mark.integration
@pytest.mark.parametrize("condition", ["suspended", "expired", "consumed", "email_changed"])
def test_ineligible_jobs_not_sent(smtp_client, smtp_account, identity_engine, condition):
    _, settings = smtp_client
    with Session(identity_engine) as session, session.begin():
        action = session.scalar(
            select(AuthAction).where(AuthAction.recipient == smtp_account["email"])
        )
        user = session.get(User, action.user_id)
        if condition == "suspended":
            user.status = "suspended"
        elif condition == "expired":
            action.created_at = datetime.now(UTC) - timedelta(hours=2)
            action.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif condition == "consumed":
            action.consumed_at = datetime.now(UTC)
        else:
            user.email = uuid4().hex + "@example.com"
    transport = CapturedTransport(identity_engine)
    assert (
        dispatch_account(identity_engine, settings, transport, smtp_account["email"])["submitted"]
        == 0
    )
    assert transport.messages == []


@pytest.mark.integration
def test_rollback_prevents_smtp(smtp_client, smtp_account, identity_engine):
    _, settings = smtp_client
    transport = CapturedTransport(identity_engine)

    def reject(session):
        raise SQLAlchemyError("simulated commit failure")

    # First isolate jobs, before installing the commit failure.
    dispatch_account(
        identity_engine,
        settings.model_copy(update={"email_provider": "outbox"}),
        transport,
        smtp_account["email"],
    )
    event.listen(Session, "before_commit", reject)
    try:
        with pytest.raises(SQLAlchemyError):
            dispatch_due_emails(identity_engine, settings, transport)
    finally:
        event.remove(Session, "before_commit", reject)
    assert transport.messages == []


@pytest.mark.integration
def test_active_lease_prevents_second_sender(smtp_client, smtp_account, identity_engine):
    _, settings = smtp_client

    class Nested(CapturedTransport):
        def send(self, message, delivery_id):
            assert dispatch_due_emails(self.engine, settings, CapturedTransport(self.engine)) == {
                "submitted": 0,
                "failed": 0,
            }
            super().send(message, delivery_id)

    transport = Nested(identity_engine)
    assert (
        dispatch_account(identity_engine, settings, transport, smtp_account["email"])["submitted"]
        == 1
    )
    assert len(transport.messages) == 1
