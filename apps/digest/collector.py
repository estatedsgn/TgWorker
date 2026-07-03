from __future__ import annotations

from datetime import timezone

from sqlalchemy import select
from telethon import TelegramClient

from apps.common.db import get_session
from apps.common.logging import get_logger
from apps.common.models import ChannelPost, DigestChannel

logger = get_logger("apps.digest.collector")

MAX_MESSAGES_PER_CHANNEL = 300
MIN_TEXT_LENGTH = 40


async def collect_channel(client: TelegramClient, channel: DigestChannel) -> int:
    entity = await client.get_entity(channel.channel_id)
    new_posts = 0
    max_seen_id = channel.last_message_id

    async for message in client.iter_messages(
        entity, min_id=channel.last_message_id, limit=MAX_MESSAGES_PER_CHANNEL
    ):
        max_seen_id = max(max_seen_id, message.id)
        text = (message.text or "").strip()
        if len(text) < MIN_TEXT_LENGTH:
            continue

        with get_session() as session:
            exists = session.scalar(
                select(ChannelPost.id).where(
                    ChannelPost.channel_id == channel.channel_id,
                    ChannelPost.tg_message_id == message.id,
                )
            )
            if exists:
                continue
            session.add(
                ChannelPost(
                    channel_id=channel.channel_id,
                    tg_message_id=message.id,
                    posted_at=message.date.astimezone(timezone.utc),
                    text=text,
                    views=getattr(message, "views", None),
                    forwards=getattr(message, "forwards", None),
                    has_media=message.media is not None,
                )
            )
            new_posts += 1

    with get_session() as session:
        db_channel = session.get(DigestChannel, channel.channel_id)
        if db_channel is not None and max_seen_id > db_channel.last_message_id:
            db_channel.last_message_id = max_seen_id

    logger.info(
        "channel collected",
        extra={"channel_id": channel.channel_id, "username": channel.username, "new": new_posts},
    )
    return new_posts


async def collect_all(client: TelegramClient) -> int:
    with get_session() as session:
        channels = session.scalars(
            select(DigestChannel).where(DigestChannel.is_active.is_(True))
        ).all()

    total = 0
    for channel in channels:
        try:
            total += await collect_channel(client, channel)
        except Exception:
            logger.exception(
                "channel collection failed",
                extra={"channel_id": channel.channel_id, "username": channel.username},
            )

    logger.info("collection finished", extra={"channels": len(channels), "new_posts": total})
    return total
