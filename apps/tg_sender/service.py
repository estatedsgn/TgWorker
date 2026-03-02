from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from apps.common.config import get_config
from apps.common.db import get_session
from apps.common.logging import get_logger
from apps.common.models import Lead, LeadStatus, Message, MessageDirection
from apps.common.telegram_client import get_client

logger = get_logger("apps.tg_sender.service")


def _is_blocked_policy(lead: Lead) -> bool:
    if not lead.consent:
        logger.info("blocked consent=false", extra={"lead_id": lead.lead_id})
        return True

    if lead.dnc or lead.status == LeadStatus.DNC.value:
        logger.info("blocked dnc", extra={"lead_id": lead.lead_id})
        return True

    return False


async def _send_via_telegram(account_id: str, target: int | str, text: str) -> int:
    client = get_client(account_id)
    await client.start()
    try:
        sent = await client.send_message(entity=target, message=text)
        return sent.id
    finally:
        await client.disconnect()


async def send_text(lead_id: str, text: str) -> Optional[int]:
    config = get_config()
    now = datetime.now(timezone.utc)

    with get_session() as session:
        lead = session.scalar(select(Lead).where(Lead.lead_id == lead_id))
        if lead is None:
            raise ValueError(f"lead not found: {lead_id}")

        if _is_blocked_policy(lead):
            return None

        if not lead.tg_peer_id and not lead.tg_username:
            lead.status = LeadStatus.ERROR.value
            lead.error = "missing peer"
            lead.updated_at = now
            logger.error("missing peer", extra={"lead_id": lead.lead_id})
            return None

        try:
            tg_message_id: Optional[int] = None
            if config.dry_run:
                logger.info("dry-run send", extra={"lead_id": lead.lead_id})
            else:
                target = lead.tg_peer_id if lead.tg_peer_id else lead.tg_username
                tg_message_id = await _send_via_telegram(lead.account_id, target=target, text=text)
                logger.info("telegram message sent", extra={"lead_id": lead.lead_id})

            session.add(
                Message(
                    lead_id=lead.lead_id,
                    direction=MessageDirection.OUT.value,
                    text=text,
                    ts=now,
                    tg_message_id=tg_message_id,
                    meta_json={"dry_run": config.dry_run},
                )
            )

            lead.last_message_out = text
            lead.last_out_at = now
            lead.attempts_count += 1
            lead.updated_at = now
            return tg_message_id
        except Exception as exc:
            lead.status = LeadStatus.ERROR.value
            lead.error = str(exc)[:500]
            lead.updated_at = now
            logger.exception("failed to send message", extra={"lead_id": lead_id})
            raise
