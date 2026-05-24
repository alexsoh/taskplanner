from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from .models import Profile, ScheduledAction
from .schemas import CalendarEvent

logger = logging.getLogger("taskplanner.calendar")


def _parse_hhmm(s: str) -> time | None:
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
    logger.info(
        "calendar query profile_id=%s actions=%d range=%s..%s",
        profile_id or "(all)",
        len(rows),
        from_date,
        to_date,
    )

    events: list[CalendarEvent] = []
    skipped_bad_time = 0
    cur = from_date
    while cur <= to_date:
        dow = cur.weekday()
        for action, profile in rows:
            if action.day_of_week != dow:
                continue
            action_time = _parse_hhmm(action.time)
            if action_time is None:
                skipped_bad_time += 1
                logger.warning(
                    "calendar skip action=%s channel=%s bad time=%r",
                    action.id,
                    action.channel,
                    action.time,
                )
                continue
            try:
                tz = ZoneInfo(profile.timezone or "UTC")
            except Exception:
                logger.warning(
                    "calendar bad timezone=%r profile=%s; using UTC",
                    profile.timezone,
                    profile.id,
                )
                tz = ZoneInfo("UTC")
            local_dt = datetime.combine(cur, action_time, tzinfo=tz)
            occurrence_utc = local_dt.astimezone(timezone.utc)
            events.append(
                CalendarEvent(
                    action_id=action.id,
                    profile_id=profile.id,
                    profile_name=profile.name,
                    profile_color=(profile.color or "#38bdf8"),
                    label=action.label,
                    channel=action.channel,
                    day_of_week=action.day_of_week,
                    time=action.time,
                    occurrence_utc=occurrence_utc,
                )
            )
        cur += timedelta(days=1)

    events.sort(key=lambda e: e.occurrence_utc)
    logger.info(
        "calendar result profile_id=%s events=%d skipped_bad_time=%d",
        profile_id or "(all)",
        len(events),
        skipped_bad_time,
    )
    return events
