"""Add durable metadata-only SMTP delivery jobs, preserving identity/action history."""

import sqlalchemy as sa
from alembic import op

revision = "0004_smtp_deliveries"
down_revision = "0003_auth_actions_outbox"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "smtp_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(40), nullable=True),
        sa.CheckConstraint(
            "provider IN ('mailtrap_sandbox', 'smtp')", name="ck_smtp_deliveries_provider"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'submitted', 'failed', 'cancelled')",
            name="ck_smtp_deliveries_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_smtp_deliveries_attempts"),
        sa.ForeignKeyConstraint(["action_id"], ["auth_actions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_id"),
    )
    op.create_index("ix_smtp_deliveries_status", "smtp_deliveries", ["status"])


def downgrade():
    op.drop_index("ix_smtp_deliveries_status", table_name="smtp_deliveries")
    op.drop_table("smtp_deliveries")
