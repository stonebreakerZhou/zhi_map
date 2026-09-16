"""Zhihu OAuth credential table.

Additive only — does not touch any pre-existing table or column.
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_zhihu_oauth"
down_revision = "0007_email_auth"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_zhihu_credentials",
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("zhihu_uid", sa.String(), nullable=False, unique=True),
        sa.Column("zhihu_name", sa.String(), nullable=True),
        sa.Column("zhihu_avatar", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )
    op.create_index(
        "ix_auth_zhihu_credentials_zhihu_uid",
        "auth_zhihu_credentials",
        ["zhihu_uid"],
        unique=True,
        if_not_exists=True,
    )


def downgrade():
    op.drop_index("ix_auth_zhihu_credentials_zhihu_uid", "auth_zhihu_credentials", if_exists=True)
    op.drop_table("auth_zhihu_credentials", if_exists=True)
