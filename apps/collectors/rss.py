from __future__ import annotations

import asyncio
import calendar
from datetime import datetime, timezone

import feedparser

from apps.collectors.base import PollingCollector, RawItem
from apps.common.logging import get_logger
from apps.pipeline.normalize import strip_html

logger = get_logger("apps.collectors.rss")

USER_AGENT = "announce-parser/0.1"


def entry_to_item(entry) -> RawItem | None:
    external_id = entry.get("id") or entry.get("link")
    if not external_id:
        return None

    title = (entry.get("title") or "").strip()
    summary = strip_html(entry.get("summary") or "").strip()
    text = f"{title}\n\n{summary}".strip()
    if not text:
        return None

    published_at: datetime | None = None
    published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if published_parsed:
        published_at = datetime.fromtimestamp(
            calendar.timegm(published_parsed), tz=timezone.utc
        )

    return RawItem(
        external_id=str(external_id),
        text=text,
        url=entry.get("link"),
        author_name=entry.get("author") or None,
        published_at=published_at,
    )


class RssCollector(PollingCollector):
    """Опрос RSS-лент фриланс-бирж (FL.ru, Freelance.ru, Weblancer и любые другие)."""

    async def poll(self, source_id: int, config: dict, state: dict) -> list[RawItem]:
        url = config["url"]
        parsed = await asyncio.to_thread(
            feedparser.parse,
            url,
            etag=state.get("etag"),
            modified=state.get("last_modified"),
            agent=USER_AGENT,
        )

        status = getattr(parsed, "status", None)
        if status == 304:
            return []
        if parsed.get("bozo") and not parsed.entries:
            raise RuntimeError(f"feed parse failed: {parsed.get('bozo_exception')}")

        if parsed.get("etag"):
            state["etag"] = parsed["etag"]
        if parsed.get("modified"):
            state["last_modified"] = parsed["modified"]

        items = []
        for entry in parsed.entries:
            item = entry_to_item(entry)
            if item is not None:
                items.append(item)
        logger.debug(
            "rss poll done", extra={"source_id": source_id, "url": url, "entries": len(items)}
        )
        return items
