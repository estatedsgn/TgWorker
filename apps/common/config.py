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
    tg_bot_token: str | None = None
    tg_bot_session_path: str = "digest_bot.session"
    llm_model: str = "claude-haiku-4-5"
    digest_allowed_user_ids: tuple[int, ...] = ()
    digest_target_chat: str = "me"
    digest_hour: int = 9
    digest_timezone: str = "Europe/Berlin"
    digest_max_items: int = 12
    digest_llm_candidates: int = 40
    digest_window_hours: int = 24
    digest_collect_interval_min: int = 30

    def safe_summary(self) -> dict[str, str | bool | int | None]:
        return {
            "app_env": self.app_env,
            "dry_run": self.dry_run,
            "log_level": self.log_level,
            "default_account_id": self.default_account_id,
            "tg_api_id_set": self.tg_api_id is not None,
            "tg_api_hash_set": self.tg_api_hash is not None,
            "tg_session_path": self.tg_session_path,
            "llm_model": self.llm_model,
            "digest_target_chat": self.digest_target_chat,
            "digest_hour": self.digest_hour,
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


def _parse_int(raw: str | None, default: int) -> int:
    if raw is None or not raw.strip():
        return default
    return int(raw.strip())


def _parse_int_list(raw: str | None) -> tuple[int, ...]:
    if raw is None or not raw.strip():
        return ()
    return tuple(int(part) for part in raw.split(",") if part.strip())


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
        tg_bot_token=os.getenv("TG_BOT_TOKEN"),
        tg_bot_session_path=os.getenv("TG_BOT_SESSION_PATH", "digest_bot.session"),
        llm_model=os.getenv("LLM_MODEL", "claude-haiku-4-5"),
        digest_allowed_user_ids=_parse_int_list(os.getenv("DIGEST_ALLOWED_USER_IDS")),
        digest_target_chat=os.getenv("DIGEST_TARGET_CHAT", "me"),
        digest_hour=_parse_int(os.getenv("DIGEST_HOUR"), 9),
        digest_timezone=os.getenv("DIGEST_TIMEZONE", "Europe/Berlin"),
        digest_max_items=_parse_int(os.getenv("DIGEST_MAX_ITEMS"), 12),
        digest_llm_candidates=_parse_int(os.getenv("DIGEST_LLM_CANDIDATES"), 40),
        digest_window_hours=_parse_int(os.getenv("DIGEST_WINDOW_HOURS"), 24),
        digest_collect_interval_min=_parse_int(os.getenv("DIGEST_COLLECT_INTERVAL_MIN"), 30),
    )
