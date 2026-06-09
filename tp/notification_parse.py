from __future__ import annotations

import logging
import uuid
from typing import Any, TypeVar

import httpx

from .notify.settings_types import (
    EvalexBackupNotification,
    EvalexCameraNotification,
    HttpNotification,
    MqttNotification,
    NvrNotification,
    ScriptNotification,
    TelegramNotification,
    _parse_http_notifications,
    _parse_nvr_notifications,
)

logger = logging.getLogger("taskplanner.notification_parse")

T = TypeVar("T")
CHANNEL_TYPES = {
    "mqtt": MqttNotification,
    "telegram": TelegramNotification,
    "http": HttpNotification,
    "script": ScriptNotification,
    "nvr": NvrNotification,
    "evalex-camera": EvalexCameraNotification,
    "evalex-backup": EvalexBackupNotification,
}


def normalize_evalex_camera_config(config: dict[str, Any]) -> dict[str, Any]:
    """Normalize Evalex camera config: ensure cameraIds is list[str], ensure notification id, prune cameraLabels."""
    normalized = dict(config) if config else {}

    camera_ids = normalized.get("cameraIds", [])
    if isinstance(camera_ids, list):
        normalized["cameraIds"] = [str(item).strip() for item in camera_ids if str(item).strip()]
    elif isinstance(camera_ids, dict):
        normalized["cameraIds"] = [str(k).strip() for k in camera_ids if str(k).strip()]
    elif camera_ids:
        normalized["cameraIds"] = [str(camera_ids).strip()]
    else:
        normalized["cameraIds"] = []

    if not normalized.get("id"):
        normalized["id"] = str(uuid.uuid4())

    if "cameraLabels" in normalized and normalized.get("cameraIds"):
        camera_ids_set = set(normalized["cameraIds"])
        labels = normalized.get("cameraLabels", {})
        if isinstance(labels, dict):
            normalized["cameraLabels"] = {k: v for k, v in labels.items() if k in camera_ids_set}

    return normalized


def normalize_evalex_backup_config(config: dict[str, Any]) -> dict[str, Any]:
    """Normalize Evalex backup config: ensure id and coerce retentionDays."""
    normalized = dict(config) if config else {}

    if not normalized.get("id"):
        normalized["id"] = str(uuid.uuid4())

    try:
        retention = int(normalized.get("retentionDays", 7))
    except (TypeError, ValueError):
        retention = 7
    normalized["retentionDays"] = max(1, retention)

    return normalized


async def reconcile_evalex_camera_config(
    config: dict[str, Any],
    logger_: logging.Logger = logger,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reconcile Evalex camera config against live server: fetch settings, keep only live camera IDs."""
    metadata: dict[str, Any] = {"stale_removed": [], "unreachable": False}

    reconciled = dict(config)

    app = (config.get("app") or "").strip().lower()
    server_address = (config.get("serverAddress") or "").strip()

    if not app or app not in ("vizmux", "piyoai", "vizrec"):
        logger_.warning(f"reconcile_evalex_camera_config: invalid app {app!r}")
        return reconciled, metadata

    if not server_address:
        logger_.warning("reconcile_evalex_camera_config: empty serverAddress")
        return reconciled, metadata

    if not server_address.startswith("http://") and not server_address.startswith("https://"):
        server_address = f"http://{server_address}"

    try:
        timeout = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            url = f"{server_address}/api/settings"
            response = await client.get(url)
            response.raise_for_status()
            settings_data = response.json()
    except Exception as e:
        logger_.warning(f"reconcile_evalex_camera_config: failed to fetch settings from {server_address}: {e}")
        metadata["unreachable"] = True
        return reconciled, metadata

    live_ids: set[str] = set()
    try:
        if app in ("vizmux", "vizrec"):
            for cam in settings_data.get("cameras", []):
                cam_id = cam.get("id", "").strip()
                if cam_id:
                    live_ids.add(cam_id)
        elif app == "piyoai":
            for folder in settings_data.get("folders", []):
                folder_id = folder.get("id", "").strip()
                if folder_id:
                    live_ids.add(folder_id)
    except Exception as e:
        logger_.warning(f"reconcile_evalex_camera_config: error parsing settings for {app}: {e}")
        return reconciled, metadata

    old_ids = set(reconciled.get("cameraIds", []))
    stale = old_ids - live_ids
    new_ids = [cid for cid in reconciled.get("cameraIds", []) if cid in live_ids]

    if stale:
        metadata["stale_removed"] = list(stale)
        logger_.info(f"reconcile_evalex_camera_config: removed stale camera IDs: {stale}")

    reconciled["cameraIds"] = new_ids

    return reconciled, metadata


def parse_notification(channel: str, config: dict[str, Any]):
    channel = (channel or "").strip().lower()
    if channel not in CHANNEL_TYPES:
        raise ValueError(f"Unknown channel: {channel}")
    cls = CHANNEL_TYPES[channel]
    if channel == "http":
        items = _parse_http_notifications([config]) if config else []
        return items[0] if items else HttpNotification()
    if channel == "nvr":
        items = _parse_nvr_notifications([config]) if config else []
        return items[0] if items else NvrNotification()
    if channel == "evalex-camera":
        obj = EvalexCameraNotification()
        for k, v in (config or {}).items():
            if k == "cameraIds":
                if isinstance(v, list):
                    obj.cameraIds = [str(item).strip() for item in v if str(item).strip()]
                elif v:
                    obj.cameraIds = [str(v).strip()]
            elif hasattr(obj, k):
                setattr(obj, k, v)
        return obj
    if channel == "evalex-backup":
        obj = EvalexBackupNotification()
        for k, v in (config or {}).items():
            if k == "retentionDays":
                try:
                    obj.retentionDays = max(1, int(v))
                except (TypeError, ValueError):
                    obj.retentionDays = 7
            elif hasattr(obj, k):
                setattr(obj, k, v)
        return obj
    obj = cls()
    for k, v in (config or {}).items():
        if hasattr(obj, k):
            setattr(obj, k, v)
    return obj
