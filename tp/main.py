import logging
import re
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import APP_DIR
from .action_runner import ActionRunError, configure_notifiers, run_scheduled_action, start_notifiers, stop_notifiers
from .calendar import expand_calendar
from .db import get_db, init_db
from .models import ExecutionRun, Profile, ScheduledAction
from .schemas import (
    ActionCreate,
    ActionOut,
    ActionUpdate,
    ExecutionOut,
    ProfileCreate,
    ProfileOut,
    ProfileUpdate,
    SettingsOut,
    SettingsUpdate,
)
from .scheduler import scheduler_loop
from .settings_store import load_mqtt_telegram, settings_to_api, update_settings

logger = logging.getLogger("taskplanner.main")

_scheduler_task = None
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
_CHANNELS = frozenset({"mqtt", "telegram", "http", "script", "nvr", "evalex"})


def _validate_time(t: str) -> None:
    if not _TIME_RE.match((t or "").strip()):
        raise HTTPException(400, "time must be HH:MM")


def _validate_channel(ch: str) -> str:
    c = (ch or "").strip().lower()
    if c not in _CHANNELS:
        raise HTTPException(400, f"channel must be one of: {', '.join(sorted(_CHANNELS))}")
    return c


def _ensure_notification_id(config: dict) -> dict:
    cfg = dict(config or {})
    if not cfg.get("id"):
        cfg["id"] = str(uuid.uuid4())
    return cfg


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _scheduler_task
    logging.basicConfig(level=logging.INFO)
    init_db()
    logger.info("TaskPlanner starting")

    from .db import SessionLocal

    db = SessionLocal()
    try:
        mqtt_s, tg_s = load_mqtt_telegram(db)
        configure_notifiers(mqtt_s, tg_s)
    finally:
        db.close()

    await start_notifiers()
    _scheduler_task = __import__("asyncio").create_task(scheduler_loop())

    yield

    if _scheduler_task:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except Exception:
            pass
    await stop_notifiers()
    logger.info("TaskPlanner stopped")


app = FastAPI(title="TaskPlanner", lifespan=lifespan)


@app.get("/api/health")
def health():
    from . import __version__

    return {"ok": True, "version": __version__}


# --- Profiles ---

@app.get("/api/profiles", response_model=list[ProfileOut])
def list_profiles(db: Session = Depends(get_db)):
    return db.query(Profile).order_by(Profile.name).all()


@app.post("/api/profiles", response_model=ProfileOut)
def create_profile(body: ProfileCreate, db: Session = Depends(get_db)):
    p = Profile(
        name=body.name,
        timezone=body.timezone,
        enabled=body.enabled,
        color=body.color,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@app.get("/api/profiles/{profile_id}", response_model=ProfileOut)
def get_profile(profile_id: str, db: Session = Depends(get_db)):
    p = db.get(Profile, profile_id)
    if not p:
        raise HTTPException(404, "Profile not found")
    return p


@app.patch("/api/profiles/{profile_id}", response_model=ProfileOut)
def update_profile(profile_id: str, body: ProfileUpdate, db: Session = Depends(get_db)):
    p = db.get(Profile, profile_id)
    if not p:
        raise HTTPException(404, "Profile not found")
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(p, field, val)
    db.commit()
    db.refresh(p)
    return p


@app.delete("/api/profiles/{profile_id}")
def delete_profile(profile_id: str, db: Session = Depends(get_db)):
    p = db.get(Profile, profile_id)
    if not p:
        raise HTTPException(404, "Profile not found")
    db.delete(p)
    db.commit()
    return {"ok": True}


# --- Actions ---

@app.get("/api/profiles/{profile_id}/actions", response_model=list[ActionOut])
def list_actions(profile_id: str, db: Session = Depends(get_db)):
    if not db.get(Profile, profile_id):
        raise HTTPException(404, "Profile not found")
    return (
        db.query(ScheduledAction)
        .filter(ScheduledAction.profile_id == profile_id)
        .order_by(ScheduledAction.day_of_week, ScheduledAction.time)
        .all()
    )


@app.post("/api/profiles/{profile_id}/actions", response_model=ActionOut)
def create_action(profile_id: str, body: ActionCreate, db: Session = Depends(get_db)):
    if not db.get(Profile, profile_id):
        raise HTTPException(404, "Profile not found")
    _validate_time(body.time)
    ch = _validate_channel(body.channel)
    a = ScheduledAction(
        profile_id=profile_id,
        label=body.label,
        day_of_week=body.day_of_week,
        time=body.time.strip(),
        channel=ch,
        enabled=body.enabled,
        notification_config=_ensure_notification_id(body.notification_config),
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@app.get("/api/actions/{action_id}", response_model=ActionOut)
def get_action(action_id: str, db: Session = Depends(get_db)):
    a = db.get(ScheduledAction, action_id)
    if not a:
        raise HTTPException(404, "Action not found")
    return a


@app.patch("/api/actions/{action_id}", response_model=ActionOut)
def update_action(action_id: str, body: ActionUpdate, db: Session = Depends(get_db)):
    a = db.get(ScheduledAction, action_id)
    if not a:
        raise HTTPException(404, "Action not found")
    data = body.model_dump(exclude_unset=True)
    if "time" in data:
        _validate_time(data["time"])
        data["time"] = data["time"].strip()
    if "channel" in data:
        data["channel"] = _validate_channel(data["channel"])
    if "notification_config" in data:
        data["notification_config"] = _ensure_notification_id(data["notification_config"])
    for field, val in data.items():
        setattr(a, field, val)
    db.commit()
    db.refresh(a)
    return a


@app.delete("/api/actions/{action_id}")
def delete_action(action_id: str, db: Session = Depends(get_db)):
    a = db.get(ScheduledAction, action_id)
    if not a:
        raise HTTPException(404, "Action not found")
    db.delete(a)
    db.commit()
    return {"ok": True}


@app.post("/api/actions/{action_id}/test")
async def test_action(action_id: str, db: Session = Depends(get_db)):
    a = db.get(ScheduledAction, action_id)
    if not a:
        raise HTTPException(404, "Action not found")
    profile = db.get(Profile, a.profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")
    mqtt_s, tg_s = load_mqtt_telegram(db)
    configure_notifiers(mqtt_s, tg_s)
    try:
        out = await run_scheduled_action(a, profile, mqtt_settings=mqtt_s, telegram_settings=tg_s)
        return out
    except ActionRunError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/discover/cameras")
async def discover_cameras(body: dict):
    """Discover cameras from a remote app (VizMux, PiyoAI, or VizRec).

    Expected body: {"app": "vizmux|piyoai|vizrec", "serverAddress": "http://host:port"}
    Returns: {"cameras": [{"id": "uuid", "name": "Camera Name"}, ...]}
    """
    import httpx

    app = (body.get("app") or "").strip().lower()
    server_address = (body.get("serverAddress") or "").strip()

    if not app:
        raise HTTPException(400, "app is required (vizmux, piyoai, or vizrec)")
    if app not in ("vizmux", "piyoai", "vizrec"):
        raise HTTPException(400, f"app must be one of: vizmux, piyoai, vizrec")
    if not server_address:
        raise HTTPException(400, "serverAddress is required")

    # Ensure proper URL format
    if not server_address.startswith("http://") and not server_address.startswith("https://"):
        server_address = f"http://{server_address}"

    try:
        timeout = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            url = f"{server_address}/api/settings"
            logger.debug(f"Discovering cameras from {app} at {url}")
            response = await client.get(url)
            response.raise_for_status()
            settings_data = response.json()

            cameras = []

            if app in ("vizmux", "vizrec"):
                # Extract cameras from cameras[] array
                for cam in settings_data.get("cameras", []):
                    cameras.append({
                        "id": cam.get("id", ""),
                        "name": cam.get("name", ""),
                    })
            elif app == "piyoai":
                # Extract cameras from folders[] array (cameras are called folders in PiyoAI)
                for folder in settings_data.get("folders", []):
                    cameras.append({
                        "id": folder.get("id", ""),
                        "name": folder.get("friendlyName", ""),
                    })

            logger.info(f"Discovered {len(cameras)} camera(s) from {app}")
            return {"cameras": cameras}

    except httpx.ConnectError:
        raise HTTPException(
            502,
            f"Failed to connect to {app} at {server_address}. Check server address and ensure the app is running.",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            504,
            f"Request to {app} timed out. The server may be unresponsive.",
        )
    except httpx.HTTPStatusError as e:
        error_text = e.response.text[:200] if hasattr(e, "response") else str(e)
        logger.warning(f"HTTP error discovering cameras: {e.status_code} - {error_text}")
        raise HTTPException(
            e.status_code,
            f"Error from {app}: {e.status_code}",
        )
    except Exception as e:
        logger.exception(f"Error discovering cameras from {app}")
        raise HTTPException(500, f"Error discovering cameras: {str(e)}")


# --- Calendar & executions ---

@app.get("/api/calendar")
def get_calendar(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    profile_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    events = expand_calendar(db, from_date, to_date, profile_id)
    return [e.model_dump(mode="json") for e in events]


@app.get("/api/executions", response_model=list[ExecutionOut])
def list_executions(
    from_dt: Optional[datetime] = Query(None, alias="from"),
    to_dt: Optional[datetime] = Query(None, alias="to"),
    profile_id: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    q = db.query(ExecutionRun).order_by(ExecutionRun.fired_at.desc())
    if from_dt:
        q = q.filter(ExecutionRun.fired_at >= from_dt)
    if to_dt:
        q = q.filter(ExecutionRun.fired_at <= to_dt)
    if profile_id:
        q = q.filter(ExecutionRun.profile_id == profile_id)
    return q.limit(limit).all()


# --- Settings ---

@app.get("/api/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    data = settings_to_api(db)
    return SettingsOut(**data)


@app.put("/api/settings", response_model=SettingsOut)
def put_settings(body: SettingsUpdate, db: Session = Depends(get_db)):
    data = update_settings(db, body.mqtt, body.telegram)
    mqtt_s, tg_s = load_mqtt_telegram(db)
    configure_notifiers(mqtt_s, tg_s)
    return SettingsOut(**data)


# --- Static UI ---

STATIC_DIR = APP_DIR / "static"
INDEX_HTML = STATIC_DIR / "index.html"


@app.get("/")
async def index():
    if INDEX_HTML.is_file():
        return FileResponse(INDEX_HTML)
    return JSONResponse(
        {"message": "TaskPlanner API", "hint": "Build frontend: cd frontend && npm run build"},
    )


if STATIC_DIR.is_dir():
    assets = STATIC_DIR / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
