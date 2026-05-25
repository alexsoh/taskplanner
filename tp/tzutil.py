from __future__ import annotations

import logging
from datetime import datetime, tzinfo, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger("taskplanner.tzutil")


def profile_timezone(name: str | None) -> tzinfo:
    """Resolve a profile timezone name; always falls back to stdlib UTC."""
    key = (name or "UTC").strip() or "UTC"
    if key.upper() in {"UTC", "ETC/UTC", "GMT", "ETC/GMT"}:
        return timezone.utc
    try:
        return ZoneInfo(key)
    except Exception:
        logger.warning("unknown timezone=%r; using UTC", name)
        return timezone.utc


def server_local_tz() -> tzinfo:
    """Host OS timezone for display and logging."""
    return datetime.now().astimezone().tzinfo or timezone.utc


def server_timezone_name() -> str:
    tz = server_local_tz()
    if hasattr(tz, "key"):
        return tz.key  # type: ignore[attr-defined]
    return str(tz)


def format_server_local(dt: datetime) -> str:
    """Format a datetime in server local time for UI/logs."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(server_local_tz())
    return local.strftime("%Y-%m-%d %H:%M:%S")
