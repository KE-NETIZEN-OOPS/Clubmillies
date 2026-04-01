"""East Africa Time (Nairobi) helpers for period filters and display."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

EAT = ZoneInfo("Africa/Nairobi")


def now_eat() -> datetime:
    return datetime.now(EAT)


def period_start_utc_naive(period: str | None) -> datetime | None:
    """
    Start of filter window in UTC (naive), for SQLAlchemy compares against stored UTC-naive datetimes.
    None = all time.
    """
    if not period or period == "all":
        return None
    now = datetime.now(EAT)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "3m":
        start = now - timedelta(days=90)
    elif period == "6m":
        start = now - timedelta(days=180)
    elif period == "year":
        start = now - timedelta(days=365)
    else:
        return None
    return start.astimezone(timezone.utc).replace(tzinfo=None)


def format_eat(iso_or_dt: str | datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    if iso_or_dt is None:
        return "—"
    if isinstance(iso_or_dt, str):
        try:
            d = datetime.fromisoformat(iso_or_dt.replace("Z", "+00:00"))
        except ValueError:
            return iso_or_dt
    else:
        d = iso_or_dt
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(EAT).strftime(fmt)
