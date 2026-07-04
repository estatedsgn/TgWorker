from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

from apps.common import db
from apps.common.models import Base


@pytest.fixture()
def session_db():
    """Чистая sqlite in-memory схема на каждый тест (engine из apps.common.db)."""
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    yield db
    Base.metadata.drop_all(db.engine)
