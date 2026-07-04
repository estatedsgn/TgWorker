from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RawItem:
    """Единица сырых данных из любого источника до фильтрации и дедупликации."""

    external_id: str
    text: str
    url: str | None = None
    author_name: str | None = None
    author_username: str | None = None
    author_id: int | None = None
    published_at: datetime | None = None


class PollingCollector(ABC):
    """Коллектор, который периодически опрашивает источник (RSS, API)."""

    @abstractmethod
    async def poll(self, source_id: int, config: dict, state: dict) -> list[RawItem]:
        """Один цикл опроса. Может мутировать state (etag и т.п.) — он сохраняется в БД."""
        raise NotImplementedError
