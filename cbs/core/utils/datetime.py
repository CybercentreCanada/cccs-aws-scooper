from datetime import datetime, timezone


def is_expired(date_string: str, format: str) -> bool:
    """Check if given date_string is in the past."""
    try:
        return datetime.now(tz=timezone.utc) >= datetime.strptime(
            date_string, format
        ).astimezone(tz=timezone.utc)
    except TypeError:
        return False
