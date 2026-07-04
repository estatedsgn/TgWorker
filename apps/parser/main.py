from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone

from sqlalchemy import select

from apps.collectors import COLLECTORS
from apps.collectors.base import PollingCollector
from apps.common.config import get_config
from apps.common.db import check_db_connection, get_session
from apps.common.logging import get_logger, setup_logging
from apps.common.models import Source
from apps.pipeline.filter import KeywordSet
from apps.pipeline.process import process_item

logger = get_logger("apps.parser.main")


def _load_enabled_sources() -> list[Source]:
    with get_session() as session:
        sources = session.execute(select(Source).where(Source.enabled.is_(True))).scalars().all()
        session.expunge_all()
    return list(sources)


def _save_poll_result(source_id: int, state: dict | None, success: bool) -> None:
    now = datetime.now(timezone.utc)
    with get_session() as session:
        source = session.get(Source, source_id)
        if source is None:
            return
        source.last_polled_at = now
        if success:
            source.last_success_at = now
            if state is not None:
                source.state = state


def _mark_backfill_done(source_id: int) -> None:
    with get_session() as session:
        source = session.get(Source, source_id)
        if source is None:
            return
        source.state = {**(source.state or {}), "backfill_done": True}


async def _poll_loop(source: Source, collector: PollingCollector, keywords: KeywordSet) -> None:
    config = get_config()
    interval = int(source.config.get("poll_interval_sec", config.rss_default_poll_sec))
    skip_filter = bool(source.config.get("skip_filter", False))
    state = dict(source.state or {})

    while True:
        try:
            items = await collector.poll(source.id, source.config, state)
            stats = {"stored": 0, "filtered": 0, "duplicate": 0}
            for item in items:
                result = await asyncio.to_thread(
                    process_item, source.id, item, keywords, skip_filter
                )
                stats[result] += 1
            await asyncio.to_thread(_save_poll_result, source.id, state, True)
            if stats["stored"]:
                logger.info(
                    "poll cycle stored announcements",
                    extra={"source_id": source.id, "source": source.name, **stats},
                )
        except Exception:
            logger.exception(
                "poll cycle failed", extra={"source_id": source.id, "source": source.name}
            )
            try:
                await asyncio.to_thread(_save_poll_result, source.id, None, False)
            except Exception:
                logger.exception("failed to record poll failure")

        await asyncio.sleep(interval * random.uniform(0.85, 1.15))


async def run() -> None:
    setup_logging()
    config = get_config()
    logger.info("starting announce-parser", extra=config.safe_summary())
    check_db_connection()

    sources = _load_enabled_sources()
    if not sources:
        logger.warning("no enabled sources in DB; run scripts/seed_sources.py first")

    keywords = KeywordSet(reload_sec=config.keywords_reload_sec)
    telegram_sources = [s for s in sources if s.type == "telegram"]
    polling_sources = [s for s in sources if s.type in COLLECTORS]
    unknown = [s for s in sources if s.type not in COLLECTORS and s.type != "telegram"]
    for src in unknown:
        logger.warning(
            "unknown source type, skipping", extra={"source_id": src.id, "type": src.type}
        )

    tasks = [
        asyncio.create_task(_poll_loop(src, COLLECTORS[src.type](), keywords))
        for src in polling_sources
    ]

    client = None
    if telegram_sources:
        from apps.collectors.telegram import register_telegram
        from apps.common.telegram_client import get_client

        client = get_client()
        await client.start()
        await register_telegram(client, telegram_sources, keywords, _mark_backfill_done)

    logger.info(
        "collectors running",
        extra={"polling": len(polling_sources), "telegram": len(telegram_sources)},
    )

    if client is not None:
        await client.run_until_disconnected()
    elif tasks:
        await asyncio.gather(*tasks)
    else:
        logger.error("nothing to do, exiting")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
