from __future__ import annotations

import asyncio
from datetime import timezone

from telethon import TelegramClient, events, utils
from telethon.tl.types import User

from apps.collectors.base import RawItem
from apps.common.logging import get_logger
from apps.common.models import Source
from apps.pipeline.filter import KeywordSet
from apps.pipeline.process import process_item

logger = get_logger("apps.collectors.telegram")


def _message_link(chat, chat_id: int, message_id: int) -> str | None:
    username = getattr(chat, "username", None)
    if username:
        return f"https://t.me/{username}/{message_id}"
    bare_id, peer_type = utils.resolve_id(chat_id)
    if peer_type.__name__ == "PeerChannel":
        return f"https://t.me/c/{bare_id}/{message_id}"
    return None


async def _message_to_item(message, chat) -> RawItem | None:
    text = (message.text or "").strip()
    if not text:
        return None

    author_name = None
    author_username = None
    author_id = None

    sender = await message.get_sender()
    if isinstance(sender, User):
        author_id = sender.id
        author_username = sender.username
        author_name = " ".join(
            part for part in (sender.first_name, sender.last_name) if part
        ) or None
    elif sender is not None:  # пост от имени канала
        author_username = getattr(sender, "username", None)
        author_name = getattr(sender, "title", None)
    if message.post_author:
        author_name = message.post_author

    chat_id = utils.get_peer_id(chat)
    published_at = message.date
    if published_at is not None and published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)

    return RawItem(
        external_id=f"{chat_id}:{message.id}",
        text=text,
        url=_message_link(chat, chat_id, message.id),
        author_name=author_name,
        author_username=author_username,
        author_id=author_id,
        published_at=published_at,
    )


async def register_telegram(
    client: TelegramClient,
    sources: list[Source],
    keywords: KeywordSet,
    mark_backfill_done,
) -> None:
    """Резолвит чаты, вешает один обработчик NewMessage, запускает backfill.

    mark_backfill_done(source_id) — колбэк для отметки state.backfill_done в БД
    (синхронный, зовётся через to_thread).
    """
    entity_map: dict[int, tuple[int, dict]] = {}
    entities = []
    backfills: list[tuple[object, int, dict]] = []

    for src in sources:
        chat_ref = src.config.get("chat")
        if not chat_ref:
            logger.warning("telegram source has no config.chat", extra={"source_id": src.id})
            continue
        try:
            entity = await client.get_entity(chat_ref)
        except Exception as exc:
            logger.warning(
                "failed to resolve chat, skipping source",
                extra={"source_id": src.id, "chat": chat_ref, "error": str(exc)},
            )
            continue
        peer_id = utils.get_peer_id(entity)
        entity_map[peer_id] = (src.id, src.config)
        entities.append(entity)

        backfill_limit = src.config.get("backfill_limit")
        if backfill_limit and not (src.state or {}).get("backfill_done"):
            backfills.append((entity, src.id, src.config))

    if not entities:
        logger.warning("no telegram sources resolved, telegram collector idle")
        return

    async def on_message(event) -> None:
        try:
            mapped = entity_map.get(event.chat_id)
            if mapped is None or event.out:
                return
            source_id, config = mapped
            chat = await event.get_chat()
            item = await _message_to_item(event.message, chat)
            if item is None:
                return
            result = await asyncio.to_thread(
                process_item, source_id, item, keywords, config.get("skip_filter", False)
            )
            logger.debug(
                "telegram message processed",
                extra={"source_id": source_id, "external_id": item.external_id, "result": result},
            )
        except Exception:
            logger.exception("telegram handler error")

    client.add_event_handler(on_message, events.NewMessage(chats=entities))
    logger.info("telegram collector listening", extra={"chats": len(entities)})

    for entity, source_id, config in backfills:
        asyncio.create_task(
            _backfill(client, entity, source_id, config, keywords, mark_backfill_done)
        )


async def _backfill(
    client: TelegramClient,
    entity,
    source_id: int,
    config: dict,
    keywords: KeywordSet,
    mark_backfill_done,
) -> None:
    limit = int(config["backfill_limit"])
    stored = 0
    try:
        async for message in client.iter_messages(entity, limit=limit):
            item = await _message_to_item(message, entity)
            if item is None:
                continue
            result = await asyncio.to_thread(
                process_item, source_id, item, keywords, config.get("skip_filter", False)
            )
            if result == "stored":
                stored += 1
        await asyncio.to_thread(mark_backfill_done, source_id)
        logger.info(
            "backfill done", extra={"source_id": source_id, "limit": limit, "stored": stored}
        )
    except Exception:
        logger.exception("backfill failed", extra={"source_id": source_id})
