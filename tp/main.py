import logging
import re
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Body
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import APP_DIR
from .action_runner import ActionRunError, configure_notifiers, run_scheduled_action, start_notifiers, stop_notifiers
from .calendar import expand_calendar
from .db import get_db, init_db
from .log_config import configure_logging
from .ip_filter import IPWhitelistMiddleware, validate_ip_or_cidr
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
from .settings_store import (
    load_mqtt_telegram,
    settings_to_api,
    update_settings,
    get_evalex_base,
    get_allowed_ips,
    get_upgrade_token,
)
from .updater import check_for_update, start_upgrade

logger = logging.getLogger("taskplanner.main")

_scheduler_task = None
_ip_middleware: Optional[IPWhitelistMiddleware] = None
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
    global _scheduler_task, _ip_middleware
    configure_logging()
    init_db()
    logger.info("TaskPlanner starting")

    from .db import SessionLocal

    db = SessionLocal()
    try:
        mqtt_s, tg_s = load_mqtt_telegram(db)
        configure_notifiers(mqtt_s, tg_s)
        
        # Initialize IP whitelist middleware
        _ip_middleware = IPWhitelistMiddleware()
        allowed_ips = get_allowed_ips(db)
        _ip_middleware.update(allowed_ips)
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


@app.middleware("http")
async def apply_ip_filter(request: Request, call_next):
    """Apply IP whitelist checks to all HTTP requests."""
    if _ip_middleware:
        client = request.client
        peer = client.host if client else None
        client_ip = _ip_middleware.effective_client_ip(peer)
        if not client_ip:
            client_ip = peer or "unknown"
        if not _ip_middleware.is_allowed(client_ip):
            logger.warning(f"Blocked request from {client_ip} (peer {peer})")
            return PlainTextResponse("403 Forbidden", status_code=403)
    return await call_next(request)


@app.get("/api/health")
def health():
    from . import __version__

    return {"ok": True, "version": __version__}


@app.get("/api/logs/{filename}")
def get_logs(filename: str):
    """Get recent log file content. Filename must be 'taskplanner' or 'upgrade'."""
    from pathlib import Path
    
    if filename not in ("taskplanner", "upgrade"):
        raise HTTPException(400, "filename must be 'taskplanner' or 'upgrade'")
    
    log_file = APP_DIR / "logs" / f"{filename}.log"
    if not log_file.exists():
        raise HTTPException(404, f"Log file not found: {filename}.log")
    
    try:
        content = log_file.read_text(encoding="utf-8", errors="ignore")
        # Return last 100 lines
        lines = content.split("\n")
        recent = "\n".join(lines[-100:])
        return {"filename": filename, "content": recent}
    except Exception as e:
        raise HTTPException(500, f"Error reading log: {e}")


@app.get("/api/version")
def get_version():
    from . import __version__

    return {"version": __version__}


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


@app.post("/api/profiles/{profile_id}/copy", response_model=ProfileOut)
def copy_profile(profile_id: str, body: ProfileCreate, db: Session = Depends(get_db)):
    source = db.get(Profile, profile_id)
    if not source:
        raise HTTPException(404, "Profile not found")
    
    new_profile = Profile(
        name=body.name,
        timezone=body.timezone or source.timezone,
        enabled=body.enabled,
        color=body.color,
    )
    db.add(new_profile)
    db.flush()
    
    for action in source.actions:
        new_action = ScheduledAction(
            profile_id=new_profile.id,
            label=action.label,
            day_of_week=action.day_of_week,
            time=action.time,
            channel=action.channel,
            enabled=action.enabled,
            notification_config=dict(action.notification_config),
        )
        db.add(new_action)
    
    db.commit()
    db.refresh(new_profile)
    return new_profile


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


@app.post("/api/actions/{action_id}/copy")
def copy_action(action_id: str, db: Session = Depends(get_db)):
    a = db.get(ScheduledAction, action_id)
    if not a:
        raise HTTPException(404, "Action not found")
    
    new_action = ScheduledAction(
        profile_id=a.profile_id,
        label=f"{a.label} (Copy)",
        day_of_week=a.day_of_week,
        time=a.time,
        channel=a.channel,
        enabled=a.enabled,
        notification_config=a.notification_config,
    )
    db.add(new_action)
    db.commit()
    db.refresh(new_action)
    return new_action


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
    logger.info(
        "GET /api/calendar from=%s to=%s profile_id=%s",
        from_date,
        to_date,
        profile_id or "(all)",
    )
    try:
        events = expand_calendar(db, from_date, to_date, profile_id)
        payload = [e.model_dump(mode="json") for e in events]
        logger.info(
            "GET /api/calendar ok events=%d profile_id=%s",
            len(payload),
            profile_id or "(all)",
        )
        return payload
    except Exception as exc:
        logger.exception(
            "GET /api/calendar failed from=%s to=%s profile_id=%s",
            from_date,
            to_date,
            profile_id or "(all)",
        )
        raise HTTPException(
            status_code=500,
            detail=f"Calendar error: {type(exc).__name__}: {exc}",
        ) from exc


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


# --- Update ---

@app.post("/api/update/check")
def check_update(body: dict = Body(default={}), db: Session = Depends(get_db)):
    token = (body.get("token") or get_upgrade_token(db)).strip()
    if not token:
        return {"error": "Please enter a Download Token and try again."}

    evalex_base = get_evalex_base(db)
    return check_for_update(token, evalex_base)


@app.post("/api/update/install")
def install_update(body: dict = Body(default={}), db: Session = Depends(get_db)):
    token = (body.get("token") or get_upgrade_token(db)).strip()
    if not token:
        return JSONResponse(
            {"error": "Please enter a Download Token and try again."},
            status_code=400,
        )

    evalex_base = get_evalex_base(db)
    result = start_upgrade(token, evalex_base)
    if "error" in result:
        return JSONResponse({"error": result["error"]}, status_code=500)

    return JSONResponse(result, status_code=202)


# --- Settings ---

@app.get("/api/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    data = settings_to_api(db)
    return SettingsOut(**data)


@app.put("/api/settings", response_model=SettingsOut)
def put_settings(body: SettingsUpdate, db: Session = Depends(get_db)):
    # Only pass fields that were actually provided in the request body
    # Use model_fields_set to detect which fields the client sent
    upgrade_token = body.upgradeToken if 'upgradeToken' in body.model_fields_set else None
    evalex_base = body.evalexBase if 'evalexBase' in body.model_fields_set else None
    allowed_ips = body.allowedIps if 'allowedIps' in body.model_fields_set else None
    server_port = body.serverPort if 'serverPort' in body.model_fields_set else None
    
    try:
        data = update_settings(db, body.mqtt if 'mqtt' in body.model_fields_set else None, 
                             body.telegram if 'telegram' in body.model_fields_set else None, 
                             upgrade_token, evalex_base, allowed_ips, server_port)
    except ValueError as e:
        raise HTTPException(400, str(e))
    
    mqtt_s, tg_s = load_mqtt_telegram(db)
    configure_notifiers(mqtt_s, tg_s)
    
    # Update IP middleware if allowed_ips changed
    if _ip_middleware and allowed_ips is not None:
        _ip_middleware.update(allowed_ips)
    
    return SettingsOut(**data)


# --- Static UI ---

STATIC_DIR = APP_DIR / "static"
INDEX_HTML = STATIC_DIR / "index.html"


@app.get("/api/server/config")
def get_server_config(db: Session = Depends(get_db)):
    """Get server configuration (port and allowed IPs)."""
    from .settings_store import get_allowed_ips, get_server_port
    
    allowed_ips = get_allowed_ips(db)
    port = get_server_port(db)
    return {"port": port, "allowedIps": allowed_ips}


@app.put("/api/server/allowed-ips")
def update_allowed_ips(body: dict, db: Session = Depends(get_db)):
    """Update the IP whitelist."""
    allowed_ips = body.get("allowedIps", [])
    if not isinstance(allowed_ips, list):
        raise HTTPException(400, "allowedIps must be a list")
    
    try:
        data = update_settings(db, None, None, allowed_ips=allowed_ips)
    except ValueError as e:
        raise HTTPException(400, str(e))
    
    # Update IP middleware
    if _ip_middleware:
        _ip_middleware.update(allowed_ips)
    
    return {"ok": True, "allowedIps": data.get("allowedIps", [])}


@app.put("/api/server/port")
def update_server_port(body: dict, db: Session = Depends(get_db)):
    """Update the server port (requires restart to take effect)."""
    port = body.get("port")
    if port is None:
        raise HTTPException(400, "port is required")
    
    try:
        port = int(port)
        if not (1 <= port <= 65535):
            raise ValueError(f"Port must be between 1 and 65535")
        data = update_settings(db, None, None, server_port=port)
    except ValueError as e:
        raise HTTPException(400, str(e))
    
    return {"ok": True, "port": data.get("serverPort"), "message": "Port changed. Restart server to apply."}


@app.post("/api/server/allow-client-ip")
def allow_client_ip(body: dict = Body(default={}), db: Session = Depends(get_db)):
    """Add an IP address to the whitelist.
    
    Can be called:
    1. With IP in body: POST {"ip": "1.2.3.4"}
    2. With empty body: POST {} - backend will detect public IP from api.ipify.org
    
    This allows external services to invoke the endpoint to whitelist themselves.
    """
    import httpx
    from .settings_store import get_allowed_ips
    
    b = body or {}
    raw_ip = str((b.get("Ip") if "Ip" in b else b.get("ip")) or "").strip()
    
    # If no IP provided, try to detect from api.ipify.org
    if not raw_ip:
        try:
            with httpx.Client(timeout=8.0) as client:
                response = client.get("https://api.ipify.org?format=json")
                response.raise_for_status()
                data = response.json()
                raw_ip = str(data.get("ip") or "").strip()
                if not raw_ip:
                    raise ValueError("Empty IP in response")
                # Validate the detected IP
                import ipaddress
                ipaddress.ip_address(raw_ip)
        except Exception as e:
            logger.warning(f"Failed to detect public IP from ipify: {e}")
            raise HTTPException(502, "Could not detect public IP. Please provide IP in request body.")
    
    # Validate IP/CIDR
    if not validate_ip_or_cidr(raw_ip):
        raise HTTPException(400, f"Invalid IP or CIDR: {raw_ip}")
    
    candidate = raw_ip.split("/")[0] if "/" in raw_ip else raw_ip
    add_entry = raw_ip
    
    allowed_ips = get_allowed_ips(db)
    
    # Check if already exists
    already = any(
        ip.split("/")[0] == candidate
        for ip in allowed_ips
    )
    
    if not already:
        allowed_ips.append(add_entry)
        try:
            data = update_settings(db, None, None, allowed_ips=allowed_ips)
        except ValueError as e:
            raise HTTPException(400, str(e))
        
        # Update IP middleware
        if _ip_middleware:
            _ip_middleware.update(data.get("allowedIps", []))
        
        logger.info(f"Added {add_entry} to IP whitelist")
        return {"ip": add_entry, "added": True, "allowedIps": data.get("allowedIps", [])}
    
    return {"ip": add_entry, "added": False, "message": "That address is already in the whitelist.", "allowedIps": allowed_ips}


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
