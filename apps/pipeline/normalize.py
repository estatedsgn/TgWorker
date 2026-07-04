from __future__ import annotations

import hashlib
import html
import re

# zero-width space/joiner/non-joiner, word joiner, BOM
_ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
_WHITESPACE_RE = re.compile(r"\s+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def normalize_text(raw: str) -> str:
    """Нормализация для матчинга и хэширования: lowercase, ё→е, без невидимых
    символов, пробельные последовательности схлопнуты в один пробел."""
    text = raw.lower().replace("ё", "е")
    text = _ZERO_WIDTH_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def text_hash(raw: str) -> str:
    return hashlib.sha256(normalize_text(raw).encode("utf-8")).hexdigest()


def strip_html(raw: str) -> str:
    """Грубая очистка HTML из RSS-описаний: теги долой, сущности раскодировать."""
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    text = _HTML_TAG_RE.sub(" ", text)
    return html.unescape(text)
