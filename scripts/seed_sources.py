"""Идемпотентный сид стартовых источников и ключевых слов.

Запуск: python scripts/seed_sources.py
Повторный запуск ничего не дублирует. Telegram-чаты добавляй сюда или прямо
в таблицу sources: INSERT INTO sources (type, name, config)
VALUES ('telegram', 'Мой чат', '{"chat": "@username"}').
"""

from __future__ import annotations

from sqlalchemy import select

from apps.common.db import get_session
from apps.common.logging import get_logger, setup_logging
from apps.common.models import Keyword, Source
from apps.pipeline.normalize import normalize_text

logger = get_logger("scripts.seed_sources")

SOURCES: list[dict] = [
    {
        "type": "rss",
        "name": "FL.ru — все проекты",
        "config": {"url": "https://www.fl.ru/rss/all.xml", "poll_interval_sec": 300},
    },
    {
        "type": "rss",
        "name": "Freelance.ru — проекты",
        "config": {"url": "https://freelance.ru/rss/all.xml", "poll_interval_sec": 300},
    },
    {
        "type": "rss",
        "name": "Weblancer — все проекты",
        "config": {"url": "https://www.weblancer.net/rss/", "poll_interval_sec": 300},
    },
    {
        "type": "freelancehunt",
        "name": "FreelanceHunt — проекты",
        # лента и так только про заказы — фильтр не нужен
        "config": {"skip_filter": True, "poll_interval_sec": 600},
    },
    # Telegram-чаты добавляются так (нужна залогиненная сессия и членство в чате):
    # {
    #     "type": "telegram",
    #     "name": "Фриланс Таверна",
    #     "config": {"chat": "@freelancetaverna", "backfill_limit": 200},
    # },
]

INCLUDE_KEYWORDS = [
    "разработчик",
    "разработать",
    "программист",
    "нужен бот",
    "нужен сайт",
    "нужно приложение",
    "сделать сайт",
    "сделать бота",
    "сделать приложение",
    "написать бота",
    "написать парсер",
    "телеграм бот",
    "telegram бот",
    "мини-приложение",
    "автоматизаци",
    "интеграци",
    "веб-приложение",
    "лендинг",
    "landing",
    "верстк",
    "backend",
    "frontend",
    "ищу того, кто сделает",
]

EXCLUDE_KEYWORDS = [
    "#резюме",
    "резюме",
    "ищу работу",
    "ищу заказы",
    "ищу проекты",
    "возьму заказ",
    "возьму в работу",
    "предлагаю услуги",
    "предлагаю свои услуги",
    "выполню ваш",
    "готов выполнить",
    "открыт к предложениям",
]


def seed() -> None:
    added_sources = 0
    added_keywords = 0
    with get_session() as session:
        for spec in SOURCES:
            exists = session.execute(
                select(Source.id).where(Source.name == spec["name"])
            ).first()
            if exists:
                continue
            session.add(Source(type=spec["type"], name=spec["name"], config=spec["config"]))
            added_sources += 1

        for kind, phrases in (("include", INCLUDE_KEYWORDS), ("exclude", EXCLUDE_KEYWORDS)):
            for raw in phrases:
                phrase = normalize_text(raw)
                exists = session.execute(
                    select(Keyword.id).where(Keyword.phrase == phrase)
                ).first()
                if exists:
                    continue
                session.add(Keyword(phrase=phrase, kind=kind))
                added_keywords += 1

    logger.info(
        "seed done", extra={"added_sources": added_sources, "added_keywords": added_keywords}
    )


if __name__ == "__main__":
    setup_logging()
    seed()
