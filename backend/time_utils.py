from datetime import datetime, timezone


def as_utc(dt: datetime | None) -> datetime | None:
    """Attach UTC tzinfo to a naive datetime before it goes into an API response.

    Every datetime in this app is naive-but-actually-UTC (datetime.utcnow() and
    Postgres timestamp-without-timezone columns). Without this, FastAPI
    serializes it with no 'Z'/offset suffix, and JS `Date.parse` then reads the
    string as local time instead of UTC -- silently corrupting every
    client-side time comparison (e.g. the assessment timer expiring
    immediately on load).
    """
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc)
