"""Evalex backup notifier - triggers settings backup on VizMux, PiyoAI, or VizRec."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .settings_types import EvalexBackupNotification

logger = logging.getLogger("taskplanner.notify.evalex_backup")

TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)


async def send_notification(
    notif: EvalexBackupNotification,
    context: Any,
    logger_: logging.Logger = logger,
) -> dict[str, Any]:
    """Trigger a settings backup on a remote app (VizMux, PiyoAI, or VizRec).

    Args:
        notif: EvalexBackupNotification with app, serverAddress, and retentionDays
        context: Dummy context (not used)
        logger_: Logger instance

    Returns:
        dict with status and backup details from the remote app

    Raises:
        httpx.RequestError or httpx.HTTPStatusError on network/HTTP errors
    """
    if not notif.enabled:
        logger_.debug("Evalex backup notification disabled, skipping")
        return {"status": "skipped", "reason": "notification_disabled"}

    if not notif.serverAddress or not notif.serverAddress.strip():
        logger_.warning("Evalex backup: serverAddress is empty")
        return {"status": "error", "error": "serverAddress is empty"}

    app = (notif.app or "").strip().lower()
    if app not in ("vizmux", "piyoai", "vizrec"):
        logger_.warning(f"Evalex backup: unknown app: {app}")
        return {"status": "error", "error": f"unknown app: {app}"}

    retention_days = int(notif.retentionDays or 7)
    if retention_days < 1:
        logger_.warning(f"Evalex backup: invalid retentionDays: {retention_days}")
        return {"status": "error", "error": "retentionDays must be >= 1"}

    server_address = notif.serverAddress.strip().rstrip("/")
    if not server_address.startswith("http://") and not server_address.startswith("https://"):
        server_address = f"http://{server_address}"

    url = f"{server_address}/api/settings/backup"
    logger_.debug(f"Calling {url} with retain={retention_days}")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(url, params={"retain": retention_days})
            response.raise_for_status()
            resp_data = response.json()
    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        logger_.warning(f"Evalex backup: HTTP error for {app}: {error_msg}")
        return {"status": "error", "error": error_msg, "app": app}
    except (httpx.RequestError, httpx.TimeoutException) as e:
        error_msg = f"Request failed: {type(e).__name__}: {str(e) or repr(e)} (URL: {url})"
        logger_.warning(f"Evalex backup: request error for {app}: {error_msg}")
        return {"status": "error", "error": error_msg, "app": app}
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger_.exception(f"Evalex backup: unexpected error for {app}")
        return {"status": "error", "error": error_msg, "app": app}

    logger_.info(f"Evalex backup: settings backup completed on {app}")
    return {"status": "ok", "app": app, "retentionDays": retention_days, **resp_data}
