from __future__ import annotations

import asyncio

from apps.common.config import get_config
from apps.common.logging import get_logger, setup_logging
from apps.common.telegram_client import get_client


async def run() -> None:
    setup_logging()
    logger = get_logger("scripts.telegram_login")
    config = get_config()

    client = get_client(config.default_account_id)
    await client.start()
    me = await client.get_me()

    logger.info(
        "telegram login successful",
        extra={
            "me_id": getattr(me, "id", None),
            "username": getattr(me, "username", None),
            "session_path": config.tg_session_path,
        },
    )

    await client.disconnect()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
