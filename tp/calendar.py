from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from .models import ScheduledAction
from .schedule_occurrences import expand_occurrences
from .schemas import CalendarEvent
from .tzutil import profile_timezone

logger = logging.getLogger("taskplanner.calendar")


def expand_calendar(
    db: Session,
    from_date: date,
    to_date: date,
    profile_id: str | None = None,
) -> list[CalendarEvent]:
    if to_date < from_date:
        return []

    since_utc = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
    until_utc = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=timezone.utc)

    action_count = (
        db.query(ScheduledAction)
        .filter(ScheduledAction.enabled.is_(True))
        .count()
    )
    logger.info(
        "calendar query profile_id=%s actions=%d range=%s..%s",
        profile_id or "(all)",
        action_count,
        from_date,
        to_date,
    )

    slots = expand_occurrences(db, since_utc, until_utc, profile_id)
    events: list[CalendarEvent] = []
    for action, profile, occurrence_utc in slots:
        tz = profile_timezone(profile.timezone)
        local = occurrence_utc.astimezone(tz)
        events.append(
            CalendarEvent(
                action_id=action.id,
                profile_id=profile.id,
                profile_name=profile.name,
                profile_color=(profile.color or "#38bdf8"),
                label=action.label,
                channel=action.channel,
                day_of_week=local.weekday(),
                time=action.time,
                occurrence_utc=occurrence_utc,
            )
        )

    logger.info(
        "calendar result profile_id=%s events=%d skipped_bad_time=0",
        profile_id or "(all)",
        len(events),
    )
    return events
