from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .action_runner import ActionRunError, configure_notifiers, run_scheduled_action
from .db import SessionLocal
from .models import ExecutionRun, Profile, ScheduledAction
from .settings_store import load_mqtt_telegram
from .tzutil import profile_timezone

logger = logging.getLogger("taskplanner.scheduler")

# Dedupe: (action_id, minute key in UTC)
_fired_keys: set[tuple[str, str]] = set()
_MAX_DEDUPE = 10_000


def _minute_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M")


def _trim_dedupe() -> None:
    global _fired_keys
    if len(_fired_keys) > _MAX_DEDUPE:
        _fired_keys = set(list(_fired_keys)[-_MAX_DEDUPE // 2 :])


def find_due_actions(db: Session, now_utc: datetime | None = None) -> list[tuple[ScheduledAction, Profile, datetime]]:
    now_utc = now_utc or datetime.now(timezone.utc)
    due: list[tuple[ScheduledAction, Profile, datetime]] = []

    rows = (
        db.query(ScheduledAction, Profile)
        .join(Profile, ScheduledAction.profile_id == Profile.id)
        .filter(ScheduledAction.enabled.is_(True), Profile.enabled.is_(True))
        .all()
    )

    for action, profile in rows:
        tz = profile_timezone(profile.timezone)
        local = now_utc.astimezone(tz)
        if local.weekday() != action.day_of_week:
            continue
        hhmm = local.strftime("%H:%M")
        if hhmm != (action.time or "").strip():
            continue
        scheduled_for = local.replace(second=0, microsecond=0).astimezone(timezone.utc)
        due.append((action, profile, scheduled_for))

    return due


async def tick_once() -> None:
    db = SessionLocal()
    try:
        mqtt_s, tg_s = load_mqtt_telegram(db)
        configure_notifiers(mqtt_s, tg_s)

        for action, profile, scheduled_for in find_due_actions(db):
            key = (action.id, _minute_key(scheduled_for))
            if key in _fired_keys:
                continue
            _fired_keys.add(key)
            _trim_dedupe()

            fired_at = datetime.now(timezone.utc)
            status = "success"
            error: str | None = None
            detail = None
            try:
                detail = await run_scheduled_action(
                    action, profile, mqtt_settings=mqtt_s, telegram_settings=tg_s,
                )
            except ActionRunError as e:
                status = "failed"
                error = str(e)
                detail = e.detail
                logger.warning("Action %s failed: %s", action.id, error)
            except Exception as e:
                status = "failed"
                error = str(e)
                logger.exception("Action %s failed", action.id)

            run = ExecutionRun(
                scheduled_action_id=action.id,
                profile_id=profile.id,
                scheduled_for=scheduled_for,
                fired_at=fired_at,
                status=status,
                error=error,
                channel=action.channel,
                label=action.label,
                detail=detail,
            )
            db.add(run)
        db.commit()
    finally:
        db.close()


async def scheduler_loop() -> None:
    logger.info("Scheduler loop started")
    while True:
        try:
            now = datetime.now(timezone.utc)
            # Align to next minute boundary
            sleep_sec = 60 - now.second - now.microsecond / 1_000_000
            if sleep_sec < 0.1:
                sleep_sec += 60
            await asyncio.sleep(sleep_sec)
            await tick_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduler tick error")
            await asyncio.sleep(5)
