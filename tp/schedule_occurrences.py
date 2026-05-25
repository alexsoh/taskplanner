from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from .models import Profile, ScheduledAction
from .tzutil import profile_timezone

Slot = tuple[ScheduledAction, Profile, datetime]


def parse_hhmm(s: str) -> time | None:
    parts = (s or "00:00").strip().split(":")
    if len(parts) < 2:
        return None
    try:
        h = int(parts[0])
        m = int(parts[1])
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return time(hour=h, minute=m)


def _query_action_rows(
    db: Session,
    profile_id: str | None = None,
    *,
    require_enabled_profile: bool = True,
) -> list[tuple[ScheduledAction, Profile]]:
    q = (
        db.query(ScheduledAction, Profile)
        .join(Profile, ScheduledAction.profile_id == Profile.id)
        .filter(ScheduledAction.enabled.is_(True))
    )
    if require_enabled_profile:
        q = q.filter(Profile.enabled.is_(True))
    if profile_id:
        q = q.filter(Profile.id == profile_id)
    return q.all()


def expand_occurrences(
    db: Session,
    since_utc: datetime,
    until_utc: datetime,
    profile_id: str | None = None,
    *,
    require_enabled_profile: bool = True,
) -> list[Slot]:
    """Return scheduled slots with scheduled_for in [since_utc, until_utc)."""
    if until_utc <= since_utc:
        return []

    rows = _query_action_rows(
        db, profile_id, require_enabled_profile=require_enabled_profile,
    )
    since_utc = since_utc.astimezone(timezone.utc)
    until_utc = until_utc.astimezone(timezone.utc)

    slots: list[Slot] = []
    for action, profile in rows:
        tz = profile_timezone(profile.timezone)
        local_since = since_utc.astimezone(tz)
        local_until = until_utc.astimezone(tz)
        cur = local_since.date()
        end_date = local_until.date()
        action_time = parse_hhmm(action.time)
        if action_time is None:
            continue

        while cur <= end_date:
            if cur.weekday() in action.days_of_week:
                local_dt = datetime.combine(cur, action_time, tzinfo=tz)
                scheduled_for = local_dt.astimezone(timezone.utc)
                if since_utc <= scheduled_for < until_utc:
                    slots.append((action, profile, scheduled_for))
            cur += timedelta(days=1)

    slots.sort(key=lambda s: s[2])
    return slots
