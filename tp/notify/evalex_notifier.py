"""Evalex notifier - enables/disables cameras on VizMux, PiyoAI, or VizRec."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

from .settings_types import EvalexCameraNotification

logger = logging.getLogger("taskplanner.notify.evalex")

TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


async def send_notification(
    notif: EvalexCameraNotification,
    context: Any,
    logger_: logging.Logger = logger,
) -> dict[str, Any]:
    """Send camera enable/disable command to a remote app (VizMux, PiyoAI, or VizRec).

    Args:
        notif: EvalexCameraNotification with app, serverAddress, cameraIds, and action
        context: Dummy context (not used for Evalex)
        logger_: Logger instance

    Returns:
        dict with status, results, and any errors

    Raises:
        httpx.RequestError or httpx.HTTPStatusError on network/HTTP errors
    """
    if not notif.enabled:
        logger_.debug("Evalex notification disabled, skipping")
        return {"status": "skipped", "reason": "notification_disabled"}

    if not notif.serverAddress or not notif.serverAddress.strip():
        logger_.warning("Evalex: serverAddress is empty")
        return {"status": "error", "error": "serverAddress is empty"}

    if not notif.cameraIds:
        logger_.warning("Evalex: no cameraIds specified")
        return {"status": "error", "error": "no cameraIds specified"}

    app = (notif.app or "").strip().lower()
    if app not in ("vizmux", "piyoai", "vizrec"):
        logger_.warning(f"Evalex: unknown app: {app}")
        return {"status": "error", "error": f"unknown app: {app}"}

    action = (notif.action or "").strip().lower()
    if action not in ("enable", "disable"):
        logger_.warning(f"Evalex: unknown action: {action}")
        return {"status": "error", "error": f"unknown action: {action}"}

    enabled_value = action == "enable"
    server_address = notif.serverAddress.strip().rstrip("/")

    # Ensure proper URL format
    if not server_address.startswith("http://") and not server_address.startswith("https://"):
        server_address = f"http://{server_address}"

    results = {"status": "ok", "app": app, "action": action, "cameras": {}}
    errors = []

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for camera_id in notif.cameraIds:
            camera_id = (camera_id or "").strip()
            if not camera_id:
                continue

            try:
                # URL-encode camera_id to prevent injection/corruption
                encoded_id = quote(camera_id, safe="")
                url = f"{server_address}/api/cameras/{encoded_id}/enabled"
                logger_.debug(f"Calling {url} with enabled={enabled_value}")

                response = await client.post(url, json={"enabled": enabled_value})
                response.raise_for_status()

                resp_data = response.json()
                results["cameras"][camera_id] = {
                    "status": "ok",
                    "enabled": resp_data.get("enabled"),
                    "changed": resp_data.get("changed", False),
                }
                logger_.info(
                    f"Evalex: {camera_id} on {app} ({action}ed) - changed={resp_data.get('changed', False)}"
                )

            except httpx.HTTPStatusError as e:
                error_msg = f"HTTP {e.status_code}: {e.response.text[:200]}"
                results["cameras"][camera_id] = {"status": "error", "error": error_msg}
                errors.append(f"{camera_id}: {error_msg}")
                logger_.warning(f"Evalex: HTTP error for {camera_id}: {error_msg}")

            except (httpx.RequestError, httpx.TimeoutException) as e:
                # Provide richer error info with URL and exception type
                error_msg = f"Request failed: {type(e).__name__}: {str(e) or repr(e)} (URL: {url})"
                results["cameras"][camera_id] = {"status": "error", "error": error_msg}
                errors.append(f"{camera_id}: {error_msg}")
                logger_.warning(f"Evalex: Request error for {camera_id}: {error_msg}")

            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                results["cameras"][camera_id] = {"status": "error", "error": error_msg}
                errors.append(f"{camera_id}: {error_msg}")
                logger_.exception(f"Evalex: Unexpected error for {camera_id}")

    if errors:
        results["errors"] = errors
        if all(cam_result.get("status") == "error" for cam_result in results["cameras"].values()):
            results["status"] = "error"
            # Set top-level error for easier surfacing
            results["error"] = errors[0] if errors else "All cameras failed"

    return results
