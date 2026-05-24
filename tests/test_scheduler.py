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
                days_of_week=[0],
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
                days_of_week=[0],
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


def test_find_due_actions_multiple_weekdays():
    """Test action fires on any of the specified weekdays."""
    db = SessionLocal()
    try:
        p = Profile(name="T", timezone="UTC", enabled=True)
        db.add(p)
        db.flush()
        db.add(
            ScheduledAction(
                profile_id=p.id,
                label="Mon/Wed/Fri",
                days_of_week=[0, 2, 4],  # Mon, Wed, Fri
                time="09:00",
                channel="http",
                enabled=True,
                notification_config={},
            )
        )
        db.commit()

        # 2026-05-18 is a Monday - should fire
        now_mon = datetime(2026, 5, 18, 9, 0, tzinfo=timezone.utc)
        due = find_due_actions(db, now_mon)
        assert len(due) == 1

        # 2026-05-19 is a Tuesday - should not fire
        now_tue = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
        due = find_due_actions(db, now_tue)
        assert len(due) == 0

        # 2026-05-20 is a Wednesday - should fire
        now_wed = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
        due = find_due_actions(db, now_wed)
        assert len(due) == 1

        # 2026-05-22 is a Friday - should fire
        now_fri = datetime(2026, 5, 22, 9, 0, tzinfo=timezone.utc)
        due = find_due_actions(db, now_fri)
        assert len(due) == 1
    finally:
        db.close()
