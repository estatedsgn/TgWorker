from __future__ import annotations

import os
from typing import Any

import socks
from telethon import TelegramClient

from apps.common.config import get_config
from apps.common.logging import get_logger

logger = get_logger("apps.common.telegram_client")

_PROXY_TYPES = {
    "SOCKS5": socks.SOCKS5,
    "SOCKS4": socks.SOCKS4,
    "HTTP": socks.HTTP,
}


def _build_proxy() -> tuple[Any, ...] | None:
    proxy_type_raw = os.getenv("PROXY_TYPE")
    proxy_host = os.getenv("PROXY_HOST")
    proxy_port = os.getenv("PROXY_PORT")

    if not proxy_type_raw or not proxy_host or not proxy_port:
        return None

    proxy_type = _PROXY_TYPES.get(proxy_type_raw.strip().upper())
    if proxy_type is None:
        raise ValueError("Unsupported PROXY_TYPE. Allowed: SOCKS5, SOCKS4, HTTP")

    proxy_user = os.getenv("PROXY_USER")
    proxy_pass = os.getenv("PROXY_PASS")
    return (proxy_type, proxy_host, int(proxy_port), True, proxy_user, proxy_pass)


def get_client(account_id: str) -> TelegramClient:
    config = get_config()
    if not config.tg_api_id or not config.tg_api_hash or not config.tg_session_path:
        raise ValueError("TG_API_ID, TG_API_HASH and TG_SESSION_PATH are required for Telegram")

    proxy = _build_proxy()
    logger.info(
        "initializing telegram client",
        extra={
            "account_id": account_id,
            "session_path": config.tg_session_path,
            "proxy_enabled": proxy is not None,
        },
    )

    return TelegramClient(
        session=config.tg_session_path,
        api_id=config.tg_api_id,
        api_hash=config.tg_api_hash,
        proxy=proxy,
    )
