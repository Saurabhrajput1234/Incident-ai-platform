from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat()


def format_datetime(dt: datetime, fmt: str = "%Y-%m-%dT%H:%M:%SZ") -> str:
    return dt.strftime(fmt)
