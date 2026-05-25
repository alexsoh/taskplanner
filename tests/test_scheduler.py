from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from tp.db import SessionLocal
from tp.models import ExecutionRun, Profile, ScheduledAction
from tp.scheduler import (
    collapse_to_latest_missed_per_action,
    collect_slots_for_tick,
    enqueue_slots,
    find_due_actions,
    find_missed_for_profile_on_activation,
    find_missed_occurrences,
    has_execution_for_slot,
    schedule_profile_activation_catchup,
    set_scheduler_loop,
    tick_once,
    try_claim_slot,
)


def _seed_profile_with_actions(
    db,
    *,
    timezone_name: str = "UTC",
    enabled: bool = True,
    actions: list[dict] | None = None,
) -> tuple[Profile, list[ScheduledAction]]:
    p = Profile(name="T", timezone=timezone_name, enabled=enabled)
    db.add(p)
    db.flush()
    created: list[ScheduledAction] = []
    for spec in actions or []:
        a = ScheduledAction(
            profile_id=p.id,
            label=spec.get("label", "X"),
            days_of_week=spec.get("days_of_week", [0]),
            time=spec["time"],
            channel=spec.get("channel", "http"),
            enabled=spec.get("enabled", True),
            notification_config=spec.get("notification_config", {"url": "http://example.com"}),
        )
        db.add(a)
        created.append(a)
    db.commit()
    return p, created


def test_find_due_actions_utc_monday_9am():
    db = SessionLocal()
    try:
        _seed_profile_with_actions(
            db,
            actions=[{"time": "09:00", "days_of_week": [0], "label": "X"}],
        )
        now = datetime(2026, 5, 18, 9, 0, tzinfo=timezone.utc)
        due = find_due_actions(db, now)
        assert len(due) == 1
        assert due[0][0].label == "X"
    finally:
        db.close()


def test_find_due_actions_wrong_time():
    db = SessionLocal()
    try:
        _seed_profile_with_actions(db, actions=[{"time": "09:00", "days_of_week": [0]}])
        now = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
        assert find_due_actions(db, now) == []
    finally:
        db.close()


def test_find_due_actions_multiple_weekdays():
    db = SessionLocal()
    try:
        _seed_profile_with_actions(
            db,
            actions=[{"time": "09:00", "days_of_week": [0, 2, 4], "label": "Mon/Wed/Fri"}],
        )
        now_mon = datetime(2026, 5, 18, 9, 0, tzinfo=timezone.utc)
        assert len(find_due_actions(db, now_mon)) == 1
        now_tue = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)
        assert find_due_actions(db, now_tue) == []
        now_wed = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
        assert len(find_due_actions(db, now_wed)) == 1
        now_fri = datetime(2026, 5, 22, 9, 0, tzinfo=timezone.utc)
        assert len(find_due_actions(db, now_fri)) == 1
    finally:
        db.close()


def test_find_due_two_actions_different_times():
    db = SessionLocal()
    try:
        _seed_profile_with_actions(
            db,
            actions=[
                {"time": "00:00", "days_of_week": [0], "label": "A"},
                {"time": "06:00", "days_of_week": [0], "label": "B"},
            ],
        )
        now_mid = datetime(2026, 5, 18, 0, 0, tzinfo=timezone.utc)
        due_mid = find_due_actions(db, now_mid)
        assert len(due_mid) == 1
        assert due_mid[0][0].label == "A"

        now_6 = datetime(2026, 5, 18, 6, 0, tzinfo=timezone.utc)
        due_6 = find_due_actions(db, now_6)
        assert len(due_6) == 1
        assert due_6[0][0].label == "B"
    finally:
        db.close()


def test_collapse_to_latest_missed_per_action():
    db = SessionLocal()
    try:
        _, actions = _seed_profile_with_actions(
            db,
            actions=[{"time": "00:00", "days_of_week": [0], "label": "A"}],
        )
        action = actions[0]
        profile = db.get(Profile, action.profile_id)
        day = datetime(2026, 5, 18, tzinfo=timezone.utc)
        slot_midnight = (action, profile, day.replace(hour=0, minute=0))
        slot_6am = (action, profile, day.replace(hour=6, minute=0))
        collapsed = collapse_to_latest_missed_per_action([slot_midnight, slot_6am])
        assert len(collapsed) == 1
        assert collapsed[0][2].hour == 6
    finally:
        db.close()


def test_find_missed_latest_only():
    db = SessionLocal()
    try:
        _seed_profile_with_actions(
            db,
            actions=[{"time": "00:00", "days_of_week": [0], "label": "A"}],
        )
        now = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
        missed = find_missed_occurrences(db, now)
        assert len(missed) == 1
        assert missed[0][2].hour == 0
    finally:
        db.close()


def test_catch_up_skips_older_occurrences():
    """Within today, only the latest missed slot per channel fires; earlier ones get skipped."""
    db = SessionLocal()
    try:
        # Two actions on the same channel scheduled at 00:00 and 06:00 today (Monday)
        p, actions = _seed_profile_with_actions(
            db,
            actions=[
                {"time": "00:00", "days_of_week": [0], "label": "Early", "channel": "http"},
                {"time": "06:00", "days_of_week": [0], "label": "Late", "channel": "http"},
            ],
        )
        early_action, late_action = actions
        # 2026-05-18 is Monday; both 00:00 and 06:00 are missed by 10:00
        now = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)

        result = find_missed_occurrences(db, now)

        # Only the latest http slot (06:00) should be returned
        assert len(result) == 1
        assert result[0][2] == datetime(2026, 5, 18, 6, 0, tzinfo=timezone.utc)
        assert result[0][0].label == "Late"

        # The 00:00 slot must have a skipped record
        early_slot = datetime(2026, 5, 18, 0, 0, tzinfo=timezone.utc)
        early_run = db.query(ExecutionRun).filter(
            ExecutionRun.scheduled_action_id == early_action.id,
            ExecutionRun.scheduled_for == early_slot,
        ).one_or_none()
        assert early_run is not None and early_run.status == "skipped"

        # Simulate enqueue claiming the 06:00 slot
        profile = db.get(Profile, late_action.profile_id)
        try_claim_slot(db, late_action, profile, datetime(2026, 5, 18, 6, 0, tzinfo=timezone.utc))

        # Subsequent find must return nothing — no double-fire
        assert find_missed_occurrences(db, now) == []
    finally:
        db.close()


def test_try_claim_slot_dedupes():
    db = SessionLocal()
    try:
        _, actions = _seed_profile_with_actions(
            db,
            actions=[{"time": "09:00", "days_of_week": [0]}],
        )
        action = actions[0]
        profile = db.get(Profile, action.profile_id)
        sf = datetime(2026, 5, 18, 9, 0, tzinfo=timezone.utc)
        assert try_claim_slot(db, action, profile, sf) is not None
        assert try_claim_slot(db, action, profile, sf) is None
        assert has_execution_for_slot(db, action.id, sf)
    finally:
        db.close()


def test_profile_activation_catchup_latest_same_day():
    db = SessionLocal()
    try:
        p, actions = _seed_profile_with_actions(
            db,
            enabled=False,
            actions=[{"time": "00:00", "days_of_week": [0], "label": "A"}],
        )
        activated_at = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
        p.enabled = True
        db.commit()
        missed = find_missed_for_profile_on_activation(db, p, activated_at)
        assert len(missed) == 1
        assert missed[0][2].hour == 0
    finally:
        db.close()


def test_profile_activation_two_actions_same_channel():
    """Two actions on the same channel — only the latest missed one fires on activation."""
    db = SessionLocal()
    try:
        p, _ = _seed_profile_with_actions(
            db,
            enabled=False,
            actions=[
                {"time": "00:00", "days_of_week": [0], "label": "A", "channel": "http"},
                {"time": "06:00", "days_of_week": [0], "label": "B", "channel": "http"},
            ],
        )
        activated_at = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
        missed = find_missed_for_profile_on_activation(db, p, activated_at)
        assert len(missed) == 1
        assert missed[0][2].hour == 6
    finally:
        db.close()


def test_tick_once_returns_before_slow_action_completes():
    async def _run():
        db = SessionLocal()
        try:
            _seed_profile_with_actions(
                db,
                actions=[{"time": "09:00", "days_of_week": [0]}],
            )
            now = datetime(2026, 5, 18, 9, 0, tzinfo=timezone.utc)

            async def slow_run(*args, **kwargs):
                await asyncio.sleep(0.2)
                return {"status": "ok"}

            set_scheduler_loop(asyncio.get_running_loop())
            with patch("tp.scheduler.find_missed_occurrences", return_value=[]), patch(
                "tp.scheduler.run_scheduled_action", new=AsyncMock(side_effect=slow_run),
            ):
                await tick_once(now)
                await asyncio.sleep(0.05)
                runs = db.query(ExecutionRun).all()
                assert len(runs) >= 1
                assert runs[0].status == "running"
                await asyncio.sleep(0.25)
                db.expire_all()
                runs = db.query(ExecutionRun).all()
                assert runs[0].status == "success"
        finally:
            db.close()

    asyncio.run(_run())


def test_tick_once_records_failed_run():
    async def _run():
        db = SessionLocal()
        try:
            _seed_profile_with_actions(
                db,
                actions=[{"time": "09:00", "days_of_week": [0]}],
            )
            now = datetime(2026, 5, 18, 9, 0, tzinfo=timezone.utc)
            from tp.action_runner import ActionRunError

            set_scheduler_loop(asyncio.get_running_loop())
            with patch("tp.scheduler.find_missed_occurrences", return_value=[]), patch(
                "tp.scheduler.run_scheduled_action",
                new=AsyncMock(side_effect=ActionRunError("boom")),
            ):
                await tick_once(now)
                await asyncio.sleep(0.1)
                run = db.query(ExecutionRun).filter(
                    ExecutionRun.scheduled_for == now.replace(second=0, microsecond=0),
                ).one()
                assert run.status == "failed"
                assert run.error == "boom"
        finally:
            db.close()

    asyncio.run(_run())


def test_concurrent_same_minute_two_actions():
    async def _run():
        db = SessionLocal()
        try:
            _seed_profile_with_actions(
                db,
                actions=[
                    {"time": "09:00", "days_of_week": [0], "label": "A"},
                    {"time": "09:00", "days_of_week": [0], "label": "B"},
                ],
            )
            now = datetime(2026, 5, 18, 9, 0, tzinfo=timezone.utc)
            started: list[str] = []

            async def track_run(action, profile, **kwargs):
                started.append(action.label)
                await asyncio.sleep(0.05)
                return {"status": "ok"}

            set_scheduler_loop(asyncio.get_running_loop())
            with patch("tp.scheduler.find_missed_occurrences", return_value=[]), patch(
                "tp.scheduler.run_scheduled_action", new=AsyncMock(side_effect=track_run),
            ):
                await tick_once(now)
                await asyncio.sleep(0.15)
                assert len(started) == 2
                assert set(started) == {"A", "B"}
                sf = now.replace(second=0, microsecond=0)
                assert db.query(ExecutionRun).filter(
                    ExecutionRun.scheduled_for == sf,
                ).count() == 2
        finally:
            db.close()

    asyncio.run(_run())
