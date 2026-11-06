"""Add single-use identity actions and encrypted durable development delivery."""

import sqlalchemy as sa
from alembic import op

revision = "0003_auth_actions_outbox"
down_revision = "0002_access_grants"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('verify_email', 'reset_password')", name="ck_auth_actions_kind"
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_auth_actions_expiry"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest"),
    )
    op.create_index("ix_auth_actions_user_id", "auth_actions", ["user_id"])
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("encrypted_payload", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["action_id"], ["auth_actions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_id"),
    )


def downgrade():
    op.drop_table("email_outbox")
    op.drop_index("ix_auth_actions_user_id", table_name="auth_actions")
    op.drop_table("auth_actions")
