from __future__ import annotations

from datetime import datetime, timezone

from tp.db import SessionLocal
from tp.models import Profile, ScheduledAction
from tp.scheduler import find_due_actions


def test_find_due_actions_utc_monday_9am():
    db = SessionLocal()
    try:
        p = Profile(name="T", timezone="UTC", enabled=True)
        db.add(p)
        db.flush()
        db.add(
            ScheduledAction(
                profile_id=p.id,
                label="X",
                day_of_week=0,
                time="09:00",
                channel="http",
                enabled=True,
                notification_config={"url": "http://example.com"},
            )
        )
        db.commit()

        # 2026-05-18 is a Monday
        now = datetime(2026, 5, 18, 9, 0, tzinfo=timezone.utc)
        due = find_due_actions(db, now)
        assert len(due) == 1
        assert due[0][0].label == "X"
    finally:
        db.close()


def test_find_due_actions_wrong_time():
    db = SessionLocal()
    try:
        p = Profile(name="T", timezone="UTC", enabled=True)
        db.add(p)
        db.flush()
        db.add(
            ScheduledAction(
                profile_id=p.id,
                label="X",
                day_of_week=0,
                time="09:00",
                channel="http",
                enabled=True,
                notification_config={},
            )
        )
        db.commit()
        now = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
        assert find_due_actions(db, now) == []
    finally:
        db.close()
