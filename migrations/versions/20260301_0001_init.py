"""init schema

Revision ID: 20260301_0001
Revises:
Create Date: 2026-03-01 00:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260301_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("account_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("timezone", sa.Text(), nullable=False, server_default=sa.text("'Europe/Berlin'")),
        sa.Column("max_messages_per_day", sa.Integer(), nullable=False),
        sa.Column("max_new_chats_per_day", sa.Integer(), nullable=False),
        sa.Column("min_delay_sec", sa.Integer(), nullable=False),
        sa.Column("max_delay_sec", sa.Integer(), nullable=False),
        sa.Column("quiet_hours_start", sa.Time(), nullable=True),
        sa.Column("quiet_hours_end", sa.Time(), nullable=True),
    )

    op.create_table(
        "leads",
        sa.Column("lead_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("account_id", sa.Text(), sa.ForeignKey("accounts.account_id"), nullable=False),
        sa.Column("tg_peer_id", sa.BigInteger(), nullable=True),
        sa.Column("tg_username", sa.Text(), nullable=True),
        sa.Column("consent", sa.Boolean(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("attempts_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("next_action_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_in", sa.Text(), nullable=True),
        sa.Column("last_message_out", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("qualification_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dnc", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_leads_account_status_next_action",
        "leads",
        ["account_id", "status", "next_action_at"],
        unique=False,
    )
    op.create_index(
        "uq_leads_account_tg_peer_id_not_null",
        "leads",
        ["account_id", "tg_peer_id"],
        unique=True,
        postgresql_where=sa.text("tg_peer_id IS NOT NULL"),
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("lead_id", sa.Text(), sa.ForeignKey("leads.lead_id"), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("tg_message_id", sa.BigInteger(), nullable=True),
        sa.Column("meta_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("ix_messages_lead_id_ts", "messages", ["lead_id", "ts"], unique=False)

    op.create_table(
        "daily_counters",
        sa.Column("account_id", sa.Text(), sa.ForeignKey("accounts.account_id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("sent_messages", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("new_threads", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("account_id", "date", name="pk_daily_counters"),
    )


def downgrade() -> None:
    op.drop_table("daily_counters")
    op.drop_index("ix_messages_lead_id_ts", table_name="messages")
    op.drop_table("messages")
    op.drop_index("uq_leads_account_tg_peer_id_not_null", table_name="leads")
    op.drop_index("ix_leads_account_status_next_action", table_name="leads")
    op.drop_table("leads")
    op.drop_table("accounts")
