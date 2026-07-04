from __future__ import annotations

from apps.collectors.base import RawItem
from apps.common.models import Keyword, Source
from apps.pipeline.filter import KeywordSet
from apps.pipeline.process import process_item


def _seed(session_db) -> tuple[int, int]:
    with session_db.get_session() as session:
        src1 = Source(type="rss", name="test feed 1", config={})
        src2 = Source(type="telegram", name="test chat", config={})
        session.add_all(
            [
                src1,
                src2,
                Keyword(phrase="разработчик", kind="include"),
                Keyword(phrase="нужен бот", kind="include"),
                Keyword(phrase="резюме", kind="exclude"),
            ]
        )
        session.flush()
        return src1.id, src2.id


def test_pipeline_store_dedup_filter(session_db):
    src1, src2 = _seed(session_db)
    keywords = KeywordSet(reload_sec=300)

    item = RawItem(external_id="a1", text="Нужен бот для магазина", url="https://x/1")
    assert process_item(src1, item, keywords) == "stored"

    # тот же external_id в том же источнике — дубликат
    assert process_item(src1, item, keywords) == "duplicate"

    # тот же текст (иное форматирование) из другого источника — hash-дубликат
    cross = RawItem(external_id="b1", text="нужен  бот для магазина\n")
    assert process_item(src2, cross, keywords) == "duplicate"

    # exclude-фраза давит include
    spam = RawItem(external_id="a2", text="Разработчик, вот моё резюме")
    assert process_item(src1, spam, keywords) == "filtered"

    # нет совпадений — отфильтровано
    junk = RawItem(external_id="a3", text="Продам гараж")
    assert process_item(src1, junk, keywords) == "filtered"

    # skip_filter пропускает нерелевантный текст
    fh = RawItem(external_id="a4", text="Project: fix CSS layout")
    assert process_item(src1, fh, keywords, skip_filter=True) == "stored"

    from sqlalchemy import select

    from apps.common.models import Announcement

    with session_db.get_session() as session:
        rows = session.execute(select(Announcement)).scalars().all()
        assert len(rows) == 2
        stored = {r.external_id: r for r in rows}
        assert stored["a1"].matched_keywords == ["нужен бот"]
        assert stored["a1"].status == "new"
        assert stored["a4"].matched_keywords == []


def test_empty_text_filtered(session_db):
    src1, _ = _seed(session_db)
    keywords = KeywordSet(reload_sec=300)
    assert process_item(src1, RawItem(external_id="e1", text="   "), keywords) == "filtered"
