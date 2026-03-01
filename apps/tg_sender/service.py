from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from apps.common.config import get_config
from apps.common.db import get_session
from apps.common.logging import get_logger
from apps.common.models import Lead, LeadStatus, Message, MessageDirection
from apps.common.telegram_client import get_client

logger = get_logger("apps.tg_sender.service")


def _validate_lead_for_send(lead: Lead) -> None:
    if not lead.consent:
        raise ValueError("lead has no consent")
    if lead.dnc or lead.status == LeadStatus.DNC.value:
        raise ValueError("lead is marked as DNC")
    if not lead.tg_peer_id and not lead.tg_username:
        raise ValueError("lead has no telegram destination")


def send_text(lead_id: str, text: str) -> None:
    config = get_config()
    now = datetime.now(timezone.utc)

    with get_session() as session:
        lead = session.scalar(select(Lead).where(Lead.lead_id == lead_id))
        if lead is None:
            raise ValueError(f"lead not found: {lead_id}")

        try:
            _validate_lead_for_send(lead)
            tg_message_id = None

            if config.dry_run:
                logger.info("dry-run send", extra={"lead_id": lead.lead_id})
            else:
                client = get_client(lead.account_id)
                with client:
                    target = lead.tg_peer_id if lead.tg_peer_id else lead.tg_username
                    sent = client.send_message(entity=target, message=text)
                    tg_message_id = sent.id
                logger.info("telegram message sent", extra={"lead_id": lead.lead_id})

            out_msg = Message(
                lead_id=lead.lead_id,
                direction=MessageDirection.OUT.value,
                text=text,
                ts=now,
                tg_message_id=tg_message_id,
                meta_json={"dry_run": config.dry_run},
            )
            session.add(out_msg)

            lead.last_message_out = text
            lead.last_out_at = now
            lead.attempts_count += 1
            lead.updated_at = now
        except Exception as exc:
            lead.status = LeadStatus.ERROR.value
            lead.error = str(exc)[:500]
            lead.updated_at = now
            logger.exception("failed to send message", extra={"lead_id": lead_id})
            raise
