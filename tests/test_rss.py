from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import feedparser

from apps.collectors.rss import entry_to_item
from apps.common.models import Keyword, Source
from apps.pipeline.filter import KeywordSet
from apps.pipeline.process import process_item

FIXTURE = Path(__file__).parent / "fixtures" / "fl_sample.xml"


def test_entry_mapping_from_fixture():
    parsed = feedparser.parse(str(FIXTURE))
    assert not parsed.bozo or parsed.entries
    items = [entry_to_item(e) for e in parsed.entries]
    assert len(items) == 3

    bot = items[0]
    assert bot.external_id == "https://www.fl.ru/projects/5111001/"
    assert bot.url == "https://www.fl.ru/projects/5111001/nuzhen-razrabotchik-telegram-bota.html"
    assert "Нужен разработчик Telegram-бота" in bot.text
    assert "Требуется сделать бота" in bot.text
    assert "<" not in bot.text  # HTML вычищен
    assert bot.published_at == datetime(2026, 7, 3, 7, 15, tzinfo=timezone.utc)


def test_fixture_through_pipeline(session_db):
    with session_db.get_session() as session:
        src = Source(type="rss", name="fl.ru", config={"url": str(FIXTURE)})
        session.add_all(
            [
                src,
                Keyword(phrase="разработчик", kind="include"),
                Keyword(phrase="сделать сайт", kind="include"),
                Keyword(phrase="сайт-визитка", kind="include"),
            ]
        )
        session.flush()
        source_id = src.id

    keywords = KeywordSet(reload_sec=300)
    parsed = feedparser.parse(str(FIXTURE))
    results = [
        process_item(source_id, entry_to_item(e), keywords) for e in parsed.entries
    ]
    # бот и сайт-визитка проходят, статья про путешествия — нет
    assert results == ["stored", "stored", "filtered"]

    # повторный прогон той же ленты — только дубликаты
    results2 = [
        process_item(source_id, entry_to_item(e), keywords) for e in parsed.entries
    ]
    assert results2 == ["duplicate", "duplicate", "filtered"]
