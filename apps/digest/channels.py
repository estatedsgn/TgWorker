from __future__ import annotations

from sqlalchemy import select
from telethon import TelegramClient

from apps.common.db import get_session
from apps.common.logging import get_logger
from apps.common.models import DigestChannel

logger = get_logger("apps.digest.channels")


async def add_channel(client: TelegramClient, identifier: str) -> DigestChannel:
    """Resolve a channel via the userbot and subscribe it for digests."""
    entity = await client.get_entity(identifier)

    channel_id = entity.id
    if getattr(entity, "broadcast", False) or getattr(entity, "megagroup", False):
        channel_id = int(f"-100{entity.id}")

    username = getattr(entity, "username", None)
    title = getattr(entity, "title", None)

    with get_session() as session:
        channel = session.get(DigestChannel, channel_id)
        if channel is not None:
            channel.is_active = True
            channel.username = username
            channel.title = title
            logger.info("channel reactivated", extra={"channel_id": channel_id})
        else:
            channel = DigestChannel(channel_id=channel_id, username=username, title=title)
            session.add(channel)
            logger.info("channel added", extra={"channel_id": channel_id, "title": title})
    return channel


def deactivate_channel(identifier: str) -> DigestChannel | None:
    username = identifier.lstrip("@").lower()
    with get_session() as session:
        channels = session.scalars(select(DigestChannel)).all()
        for channel in channels:
            matches_id = identifier.lstrip("-").isdigit() and channel.channel_id == int(identifier)
            matches_name = (channel.username or "").lower() == username
            if matches_id or matches_name:
                channel.is_active = False
                logger.info("channel deactivated", extra={"channel_id": channel.channel_id})
                return channel
    logger.warning("channel not found", extra={"identifier": identifier})
    return None


def list_channels() -> list[DigestChannel]:
    with get_session() as session:
        return list(
            session.scalars(select(DigestChannel).order_by(DigestChannel.added_at)).all()
        )
