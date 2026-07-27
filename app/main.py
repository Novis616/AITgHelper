from app.common.logging import configure_logging
from app.config.settings import get_settings


def main() -> None:
    """Minimal application entrypoint.

    Full Telegram bot startup, storage, scheduler, and AI logic are added in
    later project stages.
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    print(f"AITgHelper skeleton is ready for app_env={settings.app_env}")


if __name__ == "__main__":
    main()
