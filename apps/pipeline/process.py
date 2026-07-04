from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from apps.collectors.base import RawItem
from apps.common.db import get_session
from apps.common.logging import get_logger
from apps.common.models import Announcement
from apps.pipeline.filter import KeywordSet
from apps.pipeline.normalize import text_hash

logger = get_logger("apps.pipeline.process")


def process_item(
    source_id: int,
    item: RawItem,
    keywords: KeywordSet,
    skip_filter: bool = False,
) -> str:
    """Фильтр → дедуп → insert. Возвращает stored | filtered | duplicate."""
    if not item.text.strip():
        return "filtered"

    matched: list[str] = []
    if skip_filter:
        matched = []
    else:
        result = keywords.match(item.text)
        if result is None:
            return "filtered"
        matched = result

    item_hash = text_hash(item.text)

    with get_session() as session:
        exists = session.execute(
            select(Announcement.id).where(
                Announcement.source_id == source_id,
                Announcement.external_id == item.external_id,
            )
        ).first()
        if exists:
            return "duplicate"

        same_hash = session.execute(
            select(Announcement.id, Announcement.source_id).where(
                Announcement.text_hash == item_hash
            )
        ).first()
        if same_hash:
            logger.info(
                "duplicate_cross_source",
                extra={
                    "source_id": source_id,
                    "external_id": item.external_id,
                    "existing_announcement_id": same_hash[0],
                    "existing_source_id": same_hash[1],
                },
            )
            return "duplicate"

        session.add(
            Announcement(
                source_id=source_id,
                external_id=item.external_id,
                url=item.url,
                text=item.text,
                text_hash=item_hash,
                author_name=item.author_name,
                author_username=item.author_username,
                author_id=item.author_id,
                matched_keywords=matched,
                published_at=item.published_at,
            )
        )
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            return "duplicate"

    logger.info(
        "announcement stored",
        extra={
            "source_id": source_id,
            "external_id": item.external_id,
            "matched_keywords": matched,
        },
    )
    return "stored"
