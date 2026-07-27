from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.common.errors import ValidationError


def load_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValidationError(f"Unknown timezone: {timezone_name}") from exc


def to_utc(value: datetime, timezone_name: str) -> datetime:
    local_timezone = load_timezone(timezone_name)
    if value.tzinfo is None:
        value = value.replace(tzinfo=local_timezone)
    return value.astimezone(timezone.utc)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
