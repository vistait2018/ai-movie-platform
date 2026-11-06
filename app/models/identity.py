from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'active', 'suspended', 'deactivated')", name="ck_users_status"
        ),
        CheckConstraint(
            "status != 'active' OR email_verified_at IS NOT NULL", name="ck_users_active_verified"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(80))


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), unique=True)


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="RESTRICT"), primary_key=True
    )


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    subject_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    event: Mapped[str] = mapped_column(String(80))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AccessGrant(Base):
    """Revocable access issuance record; never stores the bearer token."""

    __tablename__ = "access_grants"
    __table_args__ = (CheckConstraint("expires_at > created_at", name="ck_access_grants_expiry"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("auth_sessions.id", ondelete="CASCADE"), index=True
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (CheckConstraint("expires_at > created_at", name="ck_auth_sessions_expiry"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(32))


class MFAFactor(Base):
    __tablename__ = "mfa_factors"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    encrypted_secret: Mapped[bytes] = mapped_column(LargeBinary)
    enrollment_session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("auth_sessions.id", ondelete="SET NULL")
    )
    enrollment_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_counter: Mapped[int] = mapped_column(default=-1)


class MFARecoveryCode(Base):
    __tablename__ = "mfa_recovery_codes"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("mfa_factors.user_id", ondelete="CASCADE"), primary_key=True
    )
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MFAAssurance(Base):
    __tablename__ = "mfa_assurances"
    __table_args__ = (CheckConstraint("expires_at > verified_at", name="ck_mfa_assurance_expiry"),)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("auth_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("mfa_factors.user_id", ondelete="CASCADE"))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RefreshCredential(Base):
    __tablename__ = "refresh_credentials"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="ck_refresh_credentials_expiry"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("auth_sessions.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("refresh_credentials.id", ondelete="SET NULL"), unique=True
    )
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthAction(Base):
    __tablename__ = "auth_actions"
    __table_args__ = (
        CheckConstraint("kind IN ('verify_email', 'reset_password')", name="ck_auth_actions_kind"),
        CheckConstraint("expires_at > created_at", name="ck_auth_actions_expiry"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    recipient: Mapped[str] = mapped_column(String(320))
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailOutbox(Base):
    """Durable encrypted development delivery; credentials never stored in plaintext."""

    __tablename__ = "email_outbox"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("auth_actions.id", ondelete="CASCADE"), unique=True
    )
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SMTPDelivery(Base):
    """SMTP job metadata only: no token, message body or SMTP credential columns."""

    __tablename__ = "smtp_deliveries"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('mailtrap_sandbox', 'smtp')", name="ck_smtp_deliveries_provider"
        ),
        CheckConstraint(
            "status IN ('pending', 'sending', 'submitted', 'failed', 'cancelled')",
            name="ck_smtp_deliveries_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_smtp_deliveries_attempts"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("auth_actions.id", ondelete="CASCADE"), unique=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", index=True
    )
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(40))
