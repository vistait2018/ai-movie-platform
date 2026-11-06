"""Add MFA factors, recovery digests and fixed-lifetime session assurance only."""

import sqlalchemy as sa
from alembic import op

revision = "0006_privileged_mfa"
down_revision = "0005_refresh_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mfa_factors",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("encrypted_secret", sa.LargeBinary(), nullable=False),
        sa.Column(
            "enrollment_session_id",
            sa.Uuid(),
            sa.ForeignKey("auth_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("enrollment_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("last_counter", sa.Integer(), nullable=False),
    )
    op.create_table(
        "mfa_recovery_codes",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("mfa_factors.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "mfa_assurances",
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("auth_sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("mfa_factors.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("expires_at > verified_at", name="ck_mfa_assurance_expiry"),
    )


def downgrade():
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE mfa_factors, mfa_recovery_codes, mfa_assurances IN ACCESS EXCLUSIVE MODE"
        )
    )
    for name in ("mfa_assurances", "mfa_recovery_codes", "mfa_factors"):
        table = sa.table(name)
        if connection.scalar(sa.select(sa.literal(1)).select_from(table).limit(1)) is not None:
            raise RuntimeError("Populated MFA tables require reviewed credential retirement")
    # Empty-schema round trips remain testable; never erase enrolled credentials.
    op.drop_table("mfa_assurances")
    op.drop_table("mfa_recovery_codes")
    op.drop_table("mfa_factors")
