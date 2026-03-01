from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from apps.common.config import get_config
from apps.common.db import get_session
from apps.common.logging import get_logger, setup_logging
from apps.common.models import Account, Lead, LeadStatus


def upsert_account(account_id: str) -> None:
    with get_session() as session:
        account = session.get(Account, account_id)
        if account is None:
            account = Account(
                account_id=account_id,
                name="Primary Account",
                is_active=True,
                timezone="Europe/Berlin",
                max_messages_per_day=50,
                max_new_chats_per_day=20,
                min_delay_sec=20,
                max_delay_sec=90,
            )
            session.add(account)
            return

        account.name = "Primary Account"
        account.is_active = True
        account.timezone = "Europe/Berlin"
        account.max_messages_per_day = 50
        account.max_new_chats_per_day = 20
        account.min_delay_sec = 20
        account.max_delay_sec = 90


def upsert_leads(account_id: str) -> None:
    now = datetime.now(timezone.utc)

    with get_session() as session:
        existing = {
            lead.lead_id: lead
            for lead in session.scalars(
                select(Lead).where(Lead.lead_id.in_(["lead_1", "lead_2"]))
            ).all()
        }

        lead_1 = existing.get("lead_1") or Lead(
            lead_id="lead_1",
            account_id=account_id,
            consent=True,
            status=LeadStatus.NEW.value,
        )
        lead_1.account_id = account_id
        lead_1.tg_username = "placeholder_consent_username"
        lead_1.next_action_at = now
        lead_1.stage = 0
        lead_1.attempts_count = 0
        lead_1.dnc = False

        lead_2 = existing.get("lead_2") or Lead(
            lead_id="lead_2",
            account_id=account_id,
            consent=False,
            status=LeadStatus.NEW.value,
        )
        lead_2.account_id = account_id
        lead_2.tg_username = None
        lead_2.next_action_at = now

        session.add(lead_1)
        session.add(lead_2)


def main() -> None:
    setup_logging()
    logger = get_logger("scripts.seed")
    config = get_config()
    upsert_account(config.default_account_id)
    upsert_leads(config.default_account_id)
    logger.info("seed completed", extra={"default_account_id": config.default_account_id})


if __name__ == "__main__":
    main()
