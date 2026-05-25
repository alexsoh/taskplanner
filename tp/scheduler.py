from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .action_runner import ActionRunError, configure_notifiers, run_scheduled_action
from .db import SessionLocal
from .models import ExecutionRun, Profile, ScheduledAction
from .schedule_occurrences import Slot, expand_occurrences
from .settings_store import load_mqtt_telegram
from .tzutil import format_server_local, profile_timezone

logger = logging.getLogger("taskplanner.scheduler")

MAX_LOOKBACK_DAYS = 7
MAX_SLOTS_ENQUEUED_PER_TICK = 50

_app_loop: asyncio.AbstractEventLoop | None = None
_in_flight: set[asyncio.Task] = set()


def set_scheduler_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _app_loop
    _app_loop = loop


def _slot_key(action_id: str, scheduled_for: datetime) -> tuple[str, datetime]:
    sf = scheduled_for.astimezone(timezone.utc).replace(second=0, microsecond=0)
    return (action_id, sf)


def has_execution_for_slot(db: Session, action_id: str, scheduled_for: datetime) -> bool:
    sf = scheduled_for.astimezone(timezone.utc).replace(second=0, microsecond=0)
    return (
        db.query(ExecutionRun.id)
        .filter(
            ExecutionRun.scheduled_action_id == action_id,
            ExecutionRun.scheduled_for == sf,
        )
        .first()
        is not None
    )


def collapse_to_latest_missed_per_action(candidates: list[Slot]) -> list[Slot]:
    best: dict[str, Slot] = {}
    for action, profile, scheduled_for in candidates:
        prev = best.get(action.id)
        if prev is None or scheduled_for > prev[2]:
            best[action.id] = (action, profile, scheduled_for)
    return list(best.values())


def find_due_actions(
    db: Session, now_utc: datetime | None = None,
) -> list[Slot]:
    now_utc = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    minute_start = now_utc.replace(second=0, microsecond=0)
    minute_end = minute_start + timedelta(minutes=1)
    return expand_occurrences(db, minute_start, minute_end)


def find_missed_occurrences(db: Session, now_utc: datetime | None = None) -> list[Slot]:
    now_utc = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    since = now_utc - timedelta(days=MAX_LOOKBACK_DAYS)
    candidates = expand_occurrences(db, since, now_utc)
    unrun = [
        slot for slot in candidates
        if not has_execution_for_slot(db, slot[0].id, slot[2])
    ]
    to_run = collapse_to_latest_missed_per_action(unrun)
    to_run_keys = {(s[0].id, s[2]) for s in to_run}
    to_skip = [s for s in unrun if (s[0].id, s[2]) not in to_run_keys]
    if to_skip:
        _mark_slots_skipped(db, to_skip)
    return to_run


def find_missed_for_profile_on_activation(
    db: Session,
    profile: Profile,
    activated_at_utc: datetime,
) -> list[Slot]:
    tz = profile_timezone(profile.timezone)
    local_activation = activated_at_utc.astimezone(tz)
    day_start_local = local_activation.replace(hour=0, minute=0, second=0, microsecond=0)
    since_utc = day_start_local.astimezone(timezone.utc)
    until_utc = activated_at_utc.astimezone(timezone.utc)

    candidates = expand_occurrences(
        db, since_utc, until_utc, profile_id=profile.id,
        require_enabled_profile=False,
    )
    unrun = [
        slot for slot in candidates
        if slot[2] < until_utc and not has_execution_for_slot(db, slot[0].id, slot[2])
    ]
    to_run = collapse_to_latest_missed_per_action(unrun)
    to_run_keys = {(s[0].id, s[2]) for s in to_run}
    to_skip = [s for s in unrun if (s[0].id, s[2]) not in to_run_keys]
    if to_skip:
        _mark_slots_skipped(db, to_skip)
    return to_run


def _dedupe_slots(slots: list[Slot]) -> list[Slot]:
    seen: set[tuple[str, datetime]] = set()
    out: list[Slot] = []
    for slot in slots:
        key = _slot_key(slot[0].id, slot[2])
        if key in seen:
            continue
        seen.add(key)
        out.append(slot)
    return out


def _mark_slots_skipped(db: Session, slots: list[Slot]) -> None:
    for action, profile, scheduled_for in slots:
        sf = scheduled_for.astimezone(timezone.utc).replace(second=0, microsecond=0)
        run = ExecutionRun(
            scheduled_action_id=action.id,
            profile_id=profile.id,
            scheduled_for=sf,
            fired_at=datetime.now(timezone.utc),
            status="skipped",
            error=None,
            channel=action.channel,
            label=action.label,
            detail=None,
        )
        db.add(run)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()


def try_claim_slot(
    db: Session,
    action: ScheduledAction,
    profile: Profile,
    scheduled_for: datetime,
) -> str | None:
    """Claim a slot; return ExecutionRun id or None if already claimed."""
    sf = scheduled_for.astimezone(timezone.utc).replace(second=0, microsecond=0)
    if has_execution_for_slot(db, action.id, sf):
        logger.debug(
            "skip already ran action_id=%s scheduled_for=%s",
            action.id,
            format_server_local(sf),
        )
        return None

    run = ExecutionRun(
        scheduled_action_id=action.id,
        profile_id=profile.id,
        scheduled_for=sf,
        fired_at=datetime.now(timezone.utc),
        status="running",
        error=None,
        channel=action.channel,
        label=action.label,
        detail=None,
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.debug(
            "slot race: already claimed action_id=%s scheduled_for=%s",
            action.id,
            format_server_local(sf),
        )
        return None
    db.refresh(run)
    return run.id


async def _fire_slot(
    run_id: str,
    action_id: str,
    profile_id: str,
    scheduled_for: datetime,
) -> None:
    db = SessionLocal()
    try:
        action = db.get(ScheduledAction, action_id)
        profile = db.get(Profile, profile_id)
        run = db.get(ExecutionRun, run_id)
        if not action or not profile or not run:
            logger.warning("slot abort missing row run=%s action=%s", run_id, action_id)
            return

        mqtt_s, tg_s = load_mqtt_telegram(db)
        configure_notifiers(mqtt_s, tg_s)

        sf = scheduled_for.astimezone(timezone.utc).replace(second=0, microsecond=0)
        logger.info(
            "slot start action_id=%s label=%r scheduled_for=%s profile=%s",
            action.id,
            action.label,
            format_server_local(sf),
            profile.name,
        )

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
            logger.warning(
                "slot failed action_id=%s scheduled_for=%s error=%s",
                action.id,
                format_server_local(sf),
                error,
            )
        except Exception as e:
            status = "failed"
            error = str(e)
            logger.exception(
                "slot failed action_id=%s scheduled_for=%s",
                action.id,
                format_server_local(sf),
            )

        run = db.get(ExecutionRun, run_id)
        if run:
            run.status = status
            run.error = error
            run.detail = detail
            run.fired_at = datetime.now(timezone.utc)
            db.commit()

        logger.info(
            "slot done action_id=%s status=%s scheduled_for=%s",
            action.id,
            status,
            format_server_local(sf),
        )
    finally:
        db.close()


def _track_task(task: asyncio.Task) -> None:
    _in_flight.add(task)
    task.add_done_callback(_in_flight.discard)


def enqueue_slots(slots: list[Slot], *, reason: str = "tick") -> int:
    """Claim and start background tasks for slots. Returns enqueue count."""
    if not slots:
        return 0

    db = SessionLocal()
    enqueued = 0
    try:
        slots = _dedupe_slots(slots)[:MAX_SLOTS_ENQUEUED_PER_TICK]
        loop = _app_loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.warning("enqueue_slots: no event loop (%s)", reason)
                return 0

        for action, profile, scheduled_for in slots:
            run_id = try_claim_slot(db, action, profile, scheduled_for)
            if not run_id:
                continue
            sf = scheduled_for.astimezone(timezone.utc).replace(second=0, microsecond=0)
            task = loop.create_task(
                _fire_slot(run_id, action.id, profile.id, sf),
            )
            _track_task(task)
            enqueued += 1
            logger.info(
                "enqueue (%s) action_id=%s label=%r scheduled_for=%s",
                reason,
                action.id,
                action.label,
                format_server_local(sf),
            )
    finally:
        db.close()
    return enqueued


def collect_slots_for_tick(db: Session, now_utc: datetime | None = None) -> tuple[list[Slot], list[Slot], list[Slot]]:
    now_utc = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    missed = find_missed_occurrences(db, now_utc)
    due = find_due_actions(db, now_utc)
    combined = _dedupe_slots(missed + due)
    return missed, due, combined


async def tick_once(now_utc: datetime | None = None) -> None:
    db = SessionLocal()
    try:
        mqtt_s, tg_s = load_mqtt_telegram(db)
        configure_notifiers(mqtt_s, tg_s)

        missed, due, combined = collect_slots_for_tick(db, now_utc)
        enqueued = enqueue_slots(combined, reason="tick")
        logger.info(
            "tick enqueued=%d missed=%d due=%d",
            enqueued,
            len(missed),
            len(due),
        )
    finally:
        db.close()


async def catch_up_missed(now_utc: datetime | None = None) -> None:
    db = SessionLocal()
    try:
        now_utc = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        missed = find_missed_occurrences(db, now_utc)
        enqueued = enqueue_slots(missed, reason="catch-up")
        logger.info(
            "catch-up starting lookback_days=%d enqueued=%d candidates=%d",
            MAX_LOOKBACK_DAYS,
            enqueued,
            len(missed),
        )
    finally:
        db.close()


def schedule_profile_activation_catchup(profile_id: str) -> None:
    """Enqueue same-day missed slots before activation time."""
    db = SessionLocal()
    try:
        profile = db.get(Profile, profile_id)
        if not profile or not profile.enabled:
            return
        activated_at = datetime.now(timezone.utc)
        slots = find_missed_for_profile_on_activation(db, profile, activated_at)
        enqueued = enqueue_slots(slots, reason="profile-activation")
        logger.info(
            "profile activation catch-up profile_id=%s name=%r enqueued=%d",
            profile_id,
            profile.name,
            enqueued,
        )
    finally:
        db.close()


def dispatch_profile_activation_catchup(profile_id: str) -> None:
    """Thread-safe entry for MQTT profile enable."""
    loop = _app_loop
    if loop is not None and loop.is_running():
        loop.call_soon_threadsafe(schedule_profile_activation_catchup, profile_id)
    else:
        schedule_profile_activation_catchup(profile_id)


async def scheduler_loop() -> None:
    set_scheduler_loop(asyncio.get_running_loop())
    logger.info("Scheduler loop started")
    await catch_up_missed()
    while True:
        try:
            now = datetime.now(timezone.utc)
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
