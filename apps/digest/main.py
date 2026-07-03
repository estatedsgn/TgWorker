from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from telethon import TelegramClient

from apps.common.config import get_config
from apps.common.db import check_db_connection, get_session
from apps.common.logging import get_logger, setup_logging
from apps.common.models import DigestChannel
from apps.common.telegram_client import get_client
from apps.digest.builder import build_digest, send_digest
from apps.digest.collector import collect_all

logger = get_logger("apps.digest")


async def _connected_client() -> TelegramClient:
    config = get_config()
    client = get_client(config.default_account_id)
    await client.start()
    return client


async def cmd_add_channel(identifier: str) -> None:
    client = await _connected_client()
    try:
        entity = await client.get_entity(identifier)
    finally:
        await client.disconnect()

    channel_id = entity.id
    if getattr(entity, "broadcast", False) or getattr(entity, "megagroup", False):
        channel_id = int(f"-100{entity.id}")

    with get_session() as session:
        existing = session.get(DigestChannel, channel_id)
        if existing:
            existing.is_active = True
            existing.username = getattr(entity, "username", None)
            existing.title = getattr(entity, "title", None)
            logger.info("channel reactivated", extra={"channel_id": channel_id})
            return
        session.add(
            DigestChannel(
                channel_id=channel_id,
                username=getattr(entity, "username", None),
                title=getattr(entity, "title", None),
            )
        )
    logger.info(
        "channel added",
        extra={"channel_id": channel_id, "title": getattr(entity, "title", None)},
    )


def cmd_remove_channel(identifier: str) -> None:
    username = identifier.lstrip("@").lower()
    with get_session() as session:
        channels = session.scalars(select(DigestChannel)).all()
        for channel in channels:
            matches_id = identifier.lstrip("-").isdigit() and channel.channel_id == int(identifier)
            matches_name = (channel.username or "").lower() == username
            if matches_id or matches_name:
                channel.is_active = False
                logger.info("channel deactivated", extra={"channel_id": channel.channel_id})
                return
    logger.warning("channel not found", extra={"identifier": identifier})


def cmd_list_channels() -> None:
    with get_session() as session:
        channels = session.scalars(select(DigestChannel).order_by(DigestChannel.added_at)).all()
        for channel in channels:
            status = "active" if channel.is_active else "inactive"
            print(f"{channel.channel_id}\t@{channel.username or '-'}\t{status}\t{channel.title}")


async def cmd_collect() -> None:
    client = await _connected_client()
    try:
        await collect_all(client)
    finally:
        await client.disconnect()


async def cmd_build(digest_date: date | None, send: bool) -> None:
    digest = build_digest(digest_date)
    if digest is None:
        print("Digest is empty: nothing interesting for this period.")
        return
    print(digest.text)
    if send:
        client = await _connected_client()
        try:
            await send_digest(client, digest.id)
        finally:
            await client.disconnect()


async def cmd_run() -> None:
    """Daemon: collect posts on an interval, build and send the digest daily."""
    config = get_config()
    tz = ZoneInfo(config.digest_timezone)
    client = await _connected_client()
    last_digest_date: date | None = None

    logger.info(
        "digest daemon started",
        extra={"digest_hour": config.digest_hour, "timezone": config.digest_timezone},
    )
    try:
        while True:
            try:
                await collect_all(client)
            except Exception:
                logger.exception("collect cycle failed")

            now_local = datetime.now(tz)
            if now_local.hour >= config.digest_hour and last_digest_date != now_local.date():
                try:
                    digest = build_digest(now_local.date())
                    if digest is not None:
                        await send_digest(client, digest.id)
                    last_digest_date = now_local.date()
                except Exception:
                    logger.exception("digest build/send failed")

            await asyncio.sleep(config.digest_collect_interval_min * 60)
    finally:
        await client.disconnect()


def main() -> None:
    setup_logging()
    config = get_config()
    logger.info("digest cli started", extra={"config": config.safe_summary()})
    check_db_connection()

    parser = argparse.ArgumentParser(prog="apps.digest")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add-channel", help="Subscribe a channel (@username or t.me link)")
    p_add.add_argument("identifier")

    p_remove = sub.add_parser("remove-channel", help="Deactivate a channel")
    p_remove.add_argument("identifier")

    sub.add_parser("list-channels", help="List subscribed channels")
    sub.add_parser("collect", help="Fetch new posts from all active channels")

    p_build = sub.add_parser("build", help="Build the digest for the last window")
    p_build.add_argument("--date", type=date.fromisoformat, default=None)
    p_build.add_argument("--send", action="store_true", help="Send the digest via Telegram")

    sub.add_parser("run", help="Daemon: collect on interval, digest daily")

    args = parser.parse_args()

    if args.command == "add-channel":
        asyncio.run(cmd_add_channel(args.identifier))
    elif args.command == "remove-channel":
        cmd_remove_channel(args.identifier)
    elif args.command == "list-channels":
        cmd_list_channels()
    elif args.command == "collect":
        asyncio.run(cmd_collect())
    elif args.command == "build":
        asyncio.run(cmd_build(args.date, args.send))
    elif args.command == "run":
        asyncio.run(cmd_run())


if __name__ == "__main__":
    main()
