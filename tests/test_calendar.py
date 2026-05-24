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
                days_of_week=[0],
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


def test_expand_calendar_multiple_weekdays():
    """Test calendar expansion with action on multiple weekdays."""
    db = SessionLocal()
    try:
        p = Profile(name="Home", timezone="UTC", enabled=True)
        db.add(p)
        db.flush()
        db.add(
            ScheduledAction(
                profile_id=p.id,
                label="Thrice weekly",
                days_of_week=[0, 2, 4],  # Mon, Wed, Fri
                time="09:00",
                channel="mqtt",
                enabled=True,
                notification_config={"topic": "test"},
            )
        )
        db.commit()

        # Week of 2026-05-18 (Mon) to 2026-05-24 (Sun)
        events = expand_calendar(db, date(2026, 5, 18), date(2026, 5, 24))
        
        # Should have 3 events: Mon (18), Wed (20), Fri (22)
        events_for_action = [e for e in events if e.label == "Thrice weekly"]
        assert len(events_for_action) == 3
        
        # Check the weekdays
        weekdays = sorted([e.day_of_week for e in events_for_action])
        assert weekdays == [0, 2, 4]
    finally:
        db.close()
