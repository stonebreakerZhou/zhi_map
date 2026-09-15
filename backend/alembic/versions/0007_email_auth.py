"""Email registration / login tables.

Additive only — does not touch any pre-existing table or column.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_email_auth"
down_revision = "0006_forest_layout"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_email_credentials",
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )
    op.create_index(
        "ix_auth_email_credentials_email",
        "auth_email_credentials",
        ["email"],
        unique=True,
        if_not_exists=True,
    )
    op.create_table(
        "auth_email_verifications",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("code_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )
    op.create_index(
        "ix_auth_email_verifications_email",
        "auth_email_verifications",
        ["email"],
        if_not_exists=True,
    )


def downgrade():
    op.drop_index("ix_auth_email_verifications_email", "auth_email_verifications", if_exists=True)
    op.drop_table("auth_email_verifications", if_exists=True)
    op.drop_index("ix_auth_email_credentials_email", "auth_email_credentials", if_exists=True)
    op.drop_table("auth_email_credentials", if_exists=True)