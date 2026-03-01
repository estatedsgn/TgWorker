"""messages in dedup index

Revision ID: 20260301_0002
Revises: 20260301_0001
Create Date: 2026-03-01 00:30:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260301_0002"
down_revision: Union[str, None] = "20260301_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_messages_in_lead_tg_message_id",
        "messages",
        ["lead_id", "tg_message_id"],
        unique=True,
        postgresql_where=sa.text("direction = 'IN' AND tg_message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_messages_in_lead_tg_message_id", table_name="messages")
