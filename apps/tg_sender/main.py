from __future__ import annotations

import argparse
import asyncio

from apps.common.logging import get_logger, setup_logging
from apps.tg_sender.service import send_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Send one Telegram text to a lead")
    parser.add_argument("lead_id")
    parser.add_argument("text")
    args = parser.parse_args()

    setup_logging()
    logger = get_logger("apps.tg_sender.main")
    tg_message_id = asyncio.run(send_text(lead_id=args.lead_id, text=args.text))
    logger.info("send finished", extra={"lead_id": args.lead_id, "tg_message_id": tg_message_id})


if __name__ == "__main__":
    main()
