from __future__ import annotations

import argparse

from apps.common.logging import setup_logging
from apps.tg_sender.service import send_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Send one Telegram text to a lead")
    parser.add_argument("lead_id")
    parser.add_argument("text")
    args = parser.parse_args()

    setup_logging()
    send_text(lead_id=args.lead_id, text=args.text)


if __name__ == "__main__":
    main()
