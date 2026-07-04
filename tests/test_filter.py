from __future__ import annotations

from apps.pipeline.filter import match_keywords
from apps.pipeline.normalize import normalize_text, strip_html, text_hash

INCLUDES = ("разработчик", "нужен бот", "сделать сайт")
EXCLUDES = ("резюме", "ищу работу")


def test_include_match_case_and_yo():
    text = normalize_text("Срочно нужен РАЗРАБОТЧИК на Django!")
    assert match_keywords(text, INCLUDES, EXCLUDES) == ["разработчик"]


def test_include_matches_plural_via_stem():
    text = normalize_text("Ищем разработчиков в команду проекта")
    assert match_keywords(text, INCLUDES, EXCLUDES) == ["разработчик"]


def test_exclude_wins_over_include():
    text = normalize_text("Разработчик, ищу работу, вот резюме")
    assert match_keywords(text, INCLUDES, EXCLUDES) is None


def test_no_match_returns_none():
    text = normalize_text("Продам гараж недорого")
    assert match_keywords(text, INCLUDES, EXCLUDES) is None


def test_multiword_phrase_across_whitespace():
    text = normalize_text("Нужен   бот\nдля телеграма")
    assert match_keywords(text, INCLUDES, EXCLUDES) == ["нужен бот"]


def test_normalize_text_yo_case_whitespace():
    assert normalize_text("  Ёлка\t и\n ещЁ  ") == "елка и еще"


def test_normalize_strips_zero_width():
    assert normalize_text("раз​работчик") == "разработчик"


def test_text_hash_stable_across_formatting():
    assert text_hash("Нужен бот!  Срочно") == text_hash("нужен бот!\nсрочно")


def test_text_hash_differs_for_different_text():
    assert text_hash("нужен бот") != text_hash("нужен сайт")


def test_strip_html():
    raw = "Нужен сайт<br/>Бюджет: <b>50&nbsp;000</b> руб."
    result = strip_html(raw)
    assert "<" not in result and ">" not in result
    assert "50\xa0000" in result
    assert "Нужен сайт\nБюджет:" in result
