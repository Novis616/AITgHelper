import asyncio

from app.bot import run_bot
from app.common.logging import configure_logging
from app.config.settings import get_settings


def main() -> None:
    """Application entrypoint for running the Telegram bot."""
    settings = get_settings()
    configure_logging(settings.log_level)
    asyncio.run(run_bot(settings))


if __name__ == "__main__":
    main()
