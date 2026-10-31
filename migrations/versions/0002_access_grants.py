"""Add revocable access issuance records without changing existing identity data."""

import sqlalchemy as sa
from alembic import op

revision = "0002_access_grants"
down_revision = "0001_identity_core"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "access_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("expires_at > created_at", name="ck_access_grants_expiry"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_access_grants_user_id", "access_grants", ["user_id"])


def downgrade():
    op.drop_index("ix_access_grants_user_id", table_name="access_grants")
    op.drop_table("access_grants")
