from __future__ import annotations

import logging
from datetime import tzinfo, timezone
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
