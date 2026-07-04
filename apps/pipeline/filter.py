from __future__ import annotations

import time

from sqlalchemy import select

from apps.common.logging import get_logger
from apps.pipeline.normalize import normalize_text

logger = get_logger("apps.pipeline.filter")


def match_keywords(
    normalized_text: str, includes: tuple[str, ...], excludes: tuple[str, ...]
) -> list[str] | None:
    """Чистая функция матчинга: None — объявление отброшено, список — совпавшие фразы."""
    for phrase in excludes:
        if phrase in normalized_text:
            return None
    matched = [phrase for phrase in includes if phrase in normalized_text]
    return matched or None


class KeywordSet:
    """Ключевые фразы из таблицы keywords с кэшем и фоновой перечиткой по TTL."""

    def __init__(self, reload_sec: int = 300) -> None:
        self._reload_sec = reload_sec
        self._loaded_at: float = 0.0
        self._includes: tuple[str, ...] = ()
        self._excludes: tuple[str, ...] = ()

    def _refresh_if_stale(self) -> None:
        if time.monotonic() - self._loaded_at < self._reload_sec and self._loaded_at:
            return
        from apps.common.db import get_session
        from apps.common.models import Keyword

        with get_session() as session:
            rows = session.execute(
                select(Keyword.phrase, Keyword.kind).where(Keyword.enabled.is_(True))
            ).all()
        includes = tuple(normalize_text(p) for p, kind in rows if kind == "include")
        excludes = tuple(normalize_text(p) for p, kind in rows if kind == "exclude")
        if (includes, excludes) != (self._includes, self._excludes):
            logger.info(
                "keywords reloaded",
                extra={"include_count": len(includes), "exclude_count": len(excludes)},
            )
        self._includes, self._excludes = includes, excludes
        self._loaded_at = time.monotonic()

    def match(self, text: str) -> list[str] | None:
        self._refresh_if_stale()
        return match_keywords(normalize_text(text), self._includes, self._excludes)
