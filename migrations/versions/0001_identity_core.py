"""Identity core and explicit role/permission seeds; additive upgrade only."""

from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op

revision = "0001_identity_core"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'suspended', 'deactivated')", name="ck_users_status"
        ),
        sa.CheckConstraint(
            "status != 'active' OR email_verified_at IS NOT NULL", name="ck_users_active_verified"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.UniqueConstraint("code", name="uq_roles_code"),
    )
    op.create_table(
        "permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_permissions"),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name="fk_user_roles_user_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], ondelete="RESTRICT", name="fk_user_roles_role_id_roles"
        ),
        sa.PrimaryKeyConstraint("user_id", "role_id", name="pk_user_roles"),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], ondelete="CASCADE", name="fk_role_permissions_role_id_roles"
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            ondelete="RESTRICT",
            name="fk_role_permissions_permission_id_permissions",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name="pk_role_permissions"),
    )
    op.create_table(
        "security_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_user_id", sa.Uuid(), nullable=True),
        sa.Column("event", sa.String(80), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["subject_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_security_events_subject_user_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_security_events"),
    )
    op.create_index("ix_security_events_subject_user_id", "security_events", ["subject_user_id"])
    roles = {
        code: uuid5(NAMESPACE_URL, f"ai-movie-platform:role:{code}")
        for code in ("viewer", "creator", "admin", "super_admin", "moderator", "finance_admin")
    }
    permissions = {
        code: uuid5(NAMESPACE_URL, f"ai-movie-platform:permission:{code}")
        for code in (
            "profile:read",
            "profile:update",
            "users:read",
            "users:manage",
            "roles:assign",
            "audit:read",
            "content:moderate",
            "finance:read",
            "projects:manage",
        )
    }
    role_table = sa.table(
        "roles",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
    )
    permission_table = sa.table(
        "permissions", sa.column("id", sa.Uuid()), sa.column("code", sa.String())
    )
    link_table = sa.table(
        "role_permissions", sa.column("role_id", sa.Uuid()), sa.column("permission_id", sa.Uuid())
    )
    op.bulk_insert(
        role_table,
        [
            {"id": value, "code": code, "name": code.replace("_", " ").title()}
            for code, value in roles.items()
        ],
    )
    op.bulk_insert(
        permission_table, [{"id": value, "code": code} for code, value in permissions.items()]
    )
    role_permissions = {
        "viewer": ["profile:read", "profile:update"],
        "creator": ["profile:read", "profile:update", "projects:manage"],
        "admin": ["users:read", "users:manage", "audit:read"],
        "super_admin": list(permissions),
        "moderator": ["content:moderate"],
        "finance_admin": ["finance:read"],
    }
    op.bulk_insert(
        link_table,
        [
            {"role_id": roles[role], "permission_id": permissions[permission]}
            for role, items in role_permissions.items()
            for permission in items
        ],
    )


def downgrade():
    # Downgrade removes identity data: test only on disposable databases, never implicit at startup.
    for table in (
        "security_events",
        "role_permissions",
        "user_roles",
        "permissions",
        "roles",
        "users",
    ):
        op.drop_table(table)
