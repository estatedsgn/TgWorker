from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from telethon import events

from apps.common.config import get_config
from apps.common.db import check_db_connection, get_session
from apps.common.logging import get_logger, setup_logging
from apps.common.models import Account, Lead, LeadStatus, Message, MessageDirection
from apps.common.telegram_client import get_client

DNC_KEYWORDS = {"не писать", "отпишись", "stop", "стоп", "unsubscribe"}


def _contains_dnc(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in DNC_KEYWORDS)


def _find_lead(session, peer_id: int, username: str | None) -> Lead | None:
    by_peer = session.scalar(select(Lead).where(Lead.tg_peer_id == peer_id))
    if by_peer:
        return by_peer

    if username:
        return session.scalar(select(Lead).where(Lead.tg_username == username))

    return None


def _is_duplicate_in_message(session, lead_id: str, tg_message_id: int | None) -> bool:
    if tg_message_id is None:
        return False

    existing = session.scalar(
        select(Message).where(
            Message.lead_id == lead_id,
            Message.direction == MessageDirection.IN.value,
            Message.tg_message_id == tg_message_id,
        )
    )
    return existing is not None


def _calc_next_action(account: Account) -> datetime:
    delay_sec = random.randint(account.min_delay_sec, account.max_delay_sec)
    return datetime.now(timezone.utc) + timedelta(seconds=delay_sec)


def main() -> None:
    setup_logging()
    logger = get_logger("apps.tg_listener")
    config = get_config()
    logger.info("listener started", extra={"config": config.safe_summary()})

    check_db_connection()
    logger.info("db connected")

    client = get_client(config.default_account_id)

    @client.on(events.NewMessage(incoming=True))
    async def on_new_message(event: events.NewMessage.Event) -> None:
        incoming_text = event.raw_text or ""
        tg_message_id = event.message.id if event.message else None
        sender = await event.get_sender()
        peer_id = sender.id if sender else None
        username = getattr(sender, "username", None)

        if peer_id is None:
            logger.info("incoming message skipped: no peer id")
            return

        with get_session() as session:
            lead = _find_lead(session, peer_id=peer_id, username=username)
            if lead is None:
                logger.info("incoming message skipped: unknown lead", extra={"peer_id": peer_id})
                return

            if _is_duplicate_in_message(session, lead.lead_id, tg_message_id):
                logger.info("incoming message skipped: duplicate", extra={"lead_id": lead.lead_id})
                return

            if _contains_dnc(incoming_text):
                lead.dnc = True
                lead.status = LeadStatus.DNC.value
                lead.last_message_in = incoming_text
                lead.last_in_at = datetime.now(timezone.utc)
                lead.updated_at = datetime.now(timezone.utc)
                session.add(
                    Message(
                        lead_id=lead.lead_id,
                        direction=MessageDirection.IN.value,
                        text=incoming_text,
                        tg_message_id=tg_message_id,
                        meta_json={"dnc_detected": True},
                    )
                )
                logger.info("lead switched to DNC", extra={"lead_id": lead.lead_id})
                return

            account = session.scalar(select(Account).where(Account.account_id == lead.account_id))
            if account is None:
                logger.error("account not found for lead", extra={"lead_id": lead.lead_id})
                return

            session.add(
                Message(
                    lead_id=lead.lead_id,
                    direction=MessageDirection.IN.value,
                    text=incoming_text,
                    tg_message_id=tg_message_id,
                    meta_json={"peer_id": peer_id, "username": username},
                )
            )

            if lead.tg_peer_id is None:
                lead.tg_peer_id = peer_id
            if username and not lead.tg_username:
                lead.tg_username = username

            lead.last_message_in = incoming_text
            lead.last_in_at = datetime.now(timezone.utc)
            if lead.status not in {LeadStatus.DNC.value, LeadStatus.ERROR.value}:
                lead.status = LeadStatus.IN_DIALOG.value
            lead.next_action_at = _calc_next_action(account)
            lead.updated_at = datetime.now(timezone.utc)

            logger.info("incoming message processed", extra={"lead_id": lead.lead_id})

    with client:
        logger.info("db connected")
        client.run_until_disconnected()


if __name__ == "__main__":
    main()
