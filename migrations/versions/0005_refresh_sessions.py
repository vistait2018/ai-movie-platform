"""Add refresh families without changing or invalidating existing access-only grants."""

import sqlalchemy as sa
from alembic import op

revision = "0005_refresh_sessions"
down_revision = "0004_smtp_deliveries"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(32), nullable=True),
        sa.CheckConstraint("expires_at > created_at", name="ck_auth_sessions_expiry"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_table(
        "refresh_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("expires_at > created_at", name="ck_refresh_credentials_expiry"),
        sa.ForeignKeyConstraint(["session_id"], ["auth_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["refresh_credentials.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest"),
        sa.UniqueConstraint("parent_id"),
    )
    op.create_index("ix_refresh_credentials_session_id", "refresh_credentials", ["session_id"])
    op.add_column("access_grants", sa.Column("session_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_access_grants_session_id_auth_sessions",
        "access_grants",
        "auth_sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_access_grants_session_id", "access_grants", ["session_id"])


def downgrade():
    # Never run against live data without first revoking the affected access credentials.
    op.drop_index("ix_access_grants_session_id", table_name="access_grants")
    op.drop_constraint(
        "fk_access_grants_session_id_auth_sessions", "access_grants", type_="foreignkey"
    )
    op.drop_column("access_grants", "session_id")
    op.drop_index("ix_refresh_credentials_session_id", table_name="refresh_credentials")
    op.drop_table("refresh_credentials")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
