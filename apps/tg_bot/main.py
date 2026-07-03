from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from telethon import TelegramClient, events

from apps.common.config import get_config
from apps.common.db import check_db_connection, get_session
from apps.common.logging import get_logger, setup_logging
from apps.common.models import Digest, DigestSubscriber
from apps.common.telegram_client import get_bot_client, get_client
from apps.digest.builder import build_digest, latest_digest_for, split_message
from apps.digest.channels import add_channel, deactivate_channel, list_channels
from apps.digest.collector import collect_all

logger = get_logger("apps.tg_bot")

HELP_TEXT = """Я собираю дайджест самого интересного из твоих Telegram-каналов за последние сутки.

Команды:
/digest — самое интересное за 1 день, прямо сейчас
/add @канал — добавить канал в подборку
/remove @канал — убрать канал
/list — список каналов
/help — эта справка

Каждый день после установленного часа я сам присылаю свежий дайджест."""


def _is_allowed(user_id: int | None) -> bool:
    allowed = get_config().digest_allowed_user_ids
    if not allowed:
        return True
    return user_id in allowed


def _subscribe(chat_id: int) -> None:
    with get_session() as session:
        subscriber = session.get(DigestSubscriber, chat_id)
        if subscriber is None:
            session.add(DigestSubscriber(chat_id=chat_id))
            logger.info("subscriber added", extra={"chat_id": chat_id})
        else:
            subscriber.is_active = True


def _active_subscribers() -> list[int]:
    with get_session() as session:
        return list(
            session.scalars(
                select(DigestSubscriber.chat_id).where(DigestSubscriber.is_active.is_(True))
            ).all()
        )


def _mark_sent(digest_id) -> None:
    with get_session() as session:
        digest = session.get(Digest, digest_id)
        if digest is not None and digest.sent_at is None:
            digest.sent_at = datetime.now(timezone.utc)


async def _send_digest(bot: TelegramClient, chat_id: int, digest: Digest) -> None:
    for part in split_message(digest.text):
        await bot.send_message(chat_id, part, parse_mode="md", link_preview=False)


async def _get_or_build_digest(digest_date: date) -> Digest | None:
    digest = latest_digest_for(digest_date)
    if digest is not None:
        return digest
    # build_digest blocks on DB + LLM HTTP; keep the bot responsive.
    return await asyncio.to_thread(build_digest, digest_date)


def _register_handlers(bot: TelegramClient, userbot: TelegramClient) -> None:
    def command(pattern: str):
        def decorator(handler):
            @bot.on(events.NewMessage(pattern=pattern, incoming=True))
            async def wrapped(event: events.NewMessage.Event) -> None:
                if not _is_allowed(event.sender_id):
                    logger.info("ignored unauthorized user", extra={"sender": event.sender_id})
                    return
                try:
                    await handler(event)
                except Exception:
                    logger.exception("command failed", extra={"text": event.raw_text[:50]})
                    await event.reply("Что-то пошло не так, посмотри логи.")

            return wrapped

        return decorator

    @command(r"^/start")
    async def on_start(event) -> None:
        _subscribe(event.chat_id)
        await event.reply(HELP_TEXT)

    @command(r"^/help")
    async def on_help(event) -> None:
        await event.reply(HELP_TEXT)

    @command(r"^/add(?:\s+(?P<ident>\S+))?")
    async def on_add(event) -> None:
        identifier = event.pattern_match.group("ident")
        if not identifier:
            await event.reply("Формат: /add @канал")
            return
        channel = await add_channel(userbot, identifier)
        title = channel.title or channel.username or str(channel.channel_id)
        await event.reply(f"Добавил канал «{title}». Посты попадут в следующий дайджест.")

    @command(r"^/remove(?:\s+(?P<ident>\S+))?")
    async def on_remove(event) -> None:
        identifier = event.pattern_match.group("ident")
        if not identifier:
            await event.reply("Формат: /remove @канал")
            return
        channel = deactivate_channel(identifier)
        if channel is None:
            await event.reply("Такого канала в подборке нет.")
        else:
            await event.reply(f"Убрал «{channel.title or identifier}» из подборки.")

    @command(r"^/list")
    async def on_list(event) -> None:
        channels = [c for c in list_channels() if c.is_active]
        if not channels:
            await event.reply("Каналов пока нет. Добавь первый: /add @канал")
            return
        lines = [
            f"• {c.title or '-'} (@{c.username})" if c.username else f"• {c.title or c.channel_id}"
            for c in channels
        ]
        await event.reply("Каналы в подборке:\n" + "\n".join(lines))

    @command(r"^/digest")
    async def on_digest(event) -> None:
        _subscribe(event.chat_id)
        await event.reply("Собираю самое интересное за последние сутки…")
        today = datetime.now(ZoneInfo(get_config().digest_timezone)).date()
        digest = await _get_or_build_digest(today)
        if digest is None:
            await event.reply(
                "За последние сутки не нашлось ничего достаточно интересного "
                "(или посты ещё не собраны — попробуй позже)."
            )
            return
        await _send_digest(bot, event.chat_id, digest)
        _mark_sent(digest.id)


async def _daily_loop(bot: TelegramClient, userbot: TelegramClient) -> None:
    """Collect posts on an interval; build and broadcast the digest once a day."""
    config = get_config()
    tz = ZoneInfo(config.digest_timezone)
    last_broadcast_date: date | None = None

    while True:
        try:
            await collect_all(userbot)
        except Exception:
            logger.exception("collect cycle failed")

        now_local = datetime.now(tz)
        if now_local.hour >= config.digest_hour and last_broadcast_date != now_local.date():
            try:
                digest = await _get_or_build_digest(now_local.date())
                if digest is not None:
                    subscribers = _active_subscribers()
                    for chat_id in subscribers:
                        try:
                            await _send_digest(bot, chat_id, digest)
                        except Exception:
                            logger.exception("broadcast failed", extra={"chat_id": chat_id})
                    _mark_sent(digest.id)
                    logger.info(
                        "digest broadcast done",
                        extra={"digest_id": str(digest.id), "subscribers": len(subscribers)},
                    )
                last_broadcast_date = now_local.date()
            except Exception:
                logger.exception("digest build/broadcast failed")

        await asyncio.sleep(config.digest_collect_interval_min * 60)


async def run_bot() -> None:
    setup_logging()
    config = get_config()
    logger.info("digest bot starting", extra={"config": config.safe_summary()})
    check_db_connection()
    logger.info("db connected")

    userbot = get_client(config.default_account_id)
    await userbot.start()
    logger.info("userbot connected")

    bot = get_bot_client()
    await bot.start(bot_token=config.tg_bot_token)
    me = await bot.get_me()
    logger.info("bot connected", extra={"bot_username": getattr(me, "username", None)})

    _register_handlers(bot, userbot)
    daily_task = asyncio.create_task(_daily_loop(bot, userbot))

    try:
        await bot.run_until_disconnected()
    finally:
        daily_task.cancel()
        await userbot.disconnect()


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
