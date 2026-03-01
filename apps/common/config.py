from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    database_url: str
    default_account_id: str
    log_level: str = "INFO"
    app_env: str = "dev"
    dry_run: bool = True
    tg_api_id: int | None = None
    tg_api_hash: str | None = None
    tg_session_path: str | None = None

    def safe_summary(self) -> dict[str, str | bool | int | None]:
        return {
            "app_env": self.app_env,
            "dry_run": self.dry_run,
            "log_level": self.log_level,
            "default_account_id": self.default_account_id,
            "tg_api_id_set": self.tg_api_id is not None,
            "tg_api_hash_set": self.tg_api_hash is not None,
            "tg_session_path": self.tg_session_path,
        }


def _parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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
        default_account_id=_required_env("DEFAULT_ACCOUNT_ID"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        app_env=os.getenv("APP_ENV", "dev"),
        dry_run=_parse_bool(os.getenv("DRY_RUN"), default=True),
        tg_api_id=int(tg_api_id_raw) if tg_api_id_raw else None,
        tg_api_hash=os.getenv("TG_API_HASH"),
        tg_session_path=os.getenv("TG_SESSION_PATH"),
    )
