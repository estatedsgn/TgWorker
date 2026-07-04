from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    database_url: str
    log_level: str = "INFO"
    app_env: str = "dev"
    tg_api_id: int | None = None
    tg_api_hash: str | None = None
    tg_session_path: str | None = None
    rss_default_poll_sec: int = 300
    keywords_reload_sec: int = 300
    freelancehunt_token: str | None = None

    def safe_summary(self) -> dict[str, str | bool | int | None]:
        return {
            "app_env": self.app_env,
            "log_level": self.log_level,
            "tg_api_id_set": self.tg_api_id is not None,
            "tg_api_hash_set": self.tg_api_hash is not None,
            "tg_session_path": self.tg_session_path,
            "rss_default_poll_sec": self.rss_default_poll_sec,
            "keywords_reload_sec": self.keywords_reload_sec,
            "freelancehunt_token_set": self.freelancehunt_token is not None,
        }


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


@lru_cache(maxsize=1)
def get_config() -> Config:
    tg_api_id_raw = os.getenv("TG_API_ID")
    return Config(
        database_url=_required_env("DATABASE_URL"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        app_env=os.getenv("APP_ENV", "dev"),
        tg_api_id=int(tg_api_id_raw) if tg_api_id_raw else None,
        tg_api_hash=os.getenv("TG_API_HASH"),
        tg_session_path=os.getenv("TG_SESSION_PATH"),
        rss_default_poll_sec=int(os.getenv("RSS_DEFAULT_POLL_SEC", "300")),
        keywords_reload_sec=int(os.getenv("KEYWORDS_RELOAD_SEC", "300")),
        freelancehunt_token=os.getenv("FREELANCEHUNT_TOKEN"),
    )
