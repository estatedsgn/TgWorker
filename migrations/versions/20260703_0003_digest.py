"""digest channels, posts and digests

Revision ID: 20260703_0003
Revises: 20260301_0002
Create Date: 2026-07-03 00:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260703_0003"
down_revision: Union[str, None] = "20260301_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "digest_channels",
        sa.Column("channel_id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_message_id", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "digests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("digest_date", sa.Date(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("items_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "channel_posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "channel_id",
            sa.BigInteger(),
            sa.ForeignKey("digest_channels.channel_id"),
            nullable=False,
        ),
        sa.Column("tg_message_id", sa.BigInteger(), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("forwards", sa.Integer(), nullable=True),
        sa.Column("has_media", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("digest_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("digests.id")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "uq_channel_posts_channel_msg",
        "channel_posts",
        ["channel_id", "tg_message_id"],
        unique=True,
    )
    op.create_index("ix_channel_posts_posted_at", "channel_posts", ["posted_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_channel_posts_posted_at", table_name="channel_posts")
    op.drop_index("uq_channel_posts_channel_msg", table_name="channel_posts")
    op.drop_table("channel_posts")
    op.drop_table("digests")
    op.drop_table("digest_channels")
