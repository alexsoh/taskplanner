from __future__ import annotations

from datetime import date

from tp.calendar import expand_calendar
from tp.db import SessionLocal
from tp.models import Profile, ScheduledAction


def test_expand_calendar_week():
    db = SessionLocal()
    try:
        p = Profile(name="Home", timezone="UTC", enabled=True)
        db.add(p)
        db.flush()
        db.add(
            ScheduledAction(
                profile_id=p.id,
                label="Morning",
                day_of_week=0,
                time="09:00",
                channel="mqtt",
                enabled=True,
                notification_config={"topic": "test"},
            )
        )
        db.commit()

        events = expand_calendar(db, date(2026, 5, 18), date(2026, 5, 24))
        assert len(events) >= 1
        assert events[0].label == "Morning"
        assert events[0].day_of_week == 0
    finally:
        db.close()
