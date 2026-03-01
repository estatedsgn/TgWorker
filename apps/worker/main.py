from apps.common.config import get_config
from apps.common.db import check_db_connection
from apps.common.logging import get_logger, setup_logging


def main() -> None:
    setup_logging()
    logger = get_logger("apps.worker")
    config = get_config()
    logger.info("worker started", extra={"config": config.safe_summary()})
    check_db_connection()
    logger.info("db connected")


if __name__ == "__main__":
    main()
