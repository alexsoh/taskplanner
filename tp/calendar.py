from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from .models import Profile, ScheduledAction
from .schemas import CalendarEvent


def _parse_hhmm(s: str) -> time:
    parts = (s or "00:00").strip().split(":")
    h = int(parts[0]) if parts else 0
    m = int(parts[1]) if len(parts) > 1 else 0
    return time(hour=h % 24, minute=m % 60)


def expand_calendar(
    db: Session,
    from_date: date,
    to_date: date,
    profile_id: str | None = None,
) -> list[CalendarEvent]:
    if to_date < from_date:
        return []

    q = (
        db.query(ScheduledAction, Profile)
        .join(Profile, ScheduledAction.profile_id == Profile.id)
        .filter(ScheduledAction.enabled.is_(True), Profile.enabled.is_(True))
    )
    if profile_id:
        q = q.filter(Profile.id == profile_id)

    rows = q.all()
    events: list[CalendarEvent] = []
    cur = from_date
    while cur <= to_date:
        # Python weekday: Mon=0 .. Sun=6 (same as our day_of_week)
        dow = cur.weekday()
        for action, profile in rows:
            if action.day_of_week != dow:
                continue
            try:
                tz = ZoneInfo(profile.timezone or "UTC")
            except Exception:
                tz = ZoneInfo("UTC")
            local_dt = datetime.combine(cur, _parse_hhmm(action.time), tzinfo=tz)
            occurrence_utc = local_dt.astimezone(timezone.utc)
            events.append(
                CalendarEvent(
                    action_id=action.id,
                    profile_id=profile.id,
                    profile_name=profile.name,
                    profile_color=profile.color,
                    label=action.label,
                    channel=action.channel,
                    day_of_week=action.day_of_week,
                    time=action.time,
                    occurrence_utc=occurrence_utc,
                )
            )
        cur += timedelta(days=1)

    events.sort(key=lambda e: e.occurrence_utc)
    return events
