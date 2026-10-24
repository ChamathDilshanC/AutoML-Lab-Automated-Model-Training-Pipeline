"""UTC helpers. SQLite does not keep time zones, so timestamps are stored as naive UTC."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def as_utc(value: datetime) -> datetime:
    """Mark a stored naive-UTC timestamp as UTC so it serialises with an explicit offset."""
    return value.replace(tzinfo=UTC)
