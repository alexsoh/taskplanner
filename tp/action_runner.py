from __future__ import annotations

import asyncio
import functools
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any, Optional

from .models import Profile, ScheduledAction
from .notification_parse import parse_notification
from .notify.evalex_notifier import send_notification as send_evalex_notification
from .notify.http_notifier import HttpNotifier
from .notify.mqtt_client import MqttClient
from .notify.nvr_notifier import NvrNotifier
from .notify import script_notifier
from .notify.settings_types import MqttSettings, TelegramSettings
from .notify.telegram_notifier import TelegramNotifier
from .schedule_context import dummy_inference_result, folder_for_profile
from .settings_store import load_mqtt_telegram

logger = logging.getLogger("taskplanner.action_runner")

mqtt = MqttClient()
telegram = TelegramNotifier()
http_notifier = HttpNotifier()
nvr_notifier = NvrNotifier()
_notify_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="taskplanner-notify")

_mqtt_settings: Optional[MqttSettings] = None
_telegram_settings: Optional[TelegramSettings] = None


def _set_profile_enabled_sync(profile_id: str, enabled: bool) -> None:
    from .db import SessionLocal
    db = SessionLocal()
    try:
        p = db.get(Profile, profile_id)
        if not p:
            logger.warning("Profile listener: profile not found: %s", profile_id)
            return
        if enabled:
            db.query(Profile).filter(Profile.id != profile_id).update({"enabled": False})
        p.enabled = enabled
        db.commit()
        logger.info("Profile listener: %s profile '%s'", "enabled" if enabled else "disabled", p.name)
        if enabled:
            from .scheduler import dispatch_profile_activation_catchup
            dispatch_profile_activation_catchup(profile_id)
    except Exception:
        db.rollback()
        logger.error("Profile listener: failed to update profile %s", profile_id, exc_info=True)
    finally:
        db.close()


def configure_notifiers(mqtt_settings: MqttSettings, telegram_settings: TelegramSettings) -> None:
    global _mqtt_settings, _telegram_settings
    _mqtt_settings = mqtt_settings
    _telegram_settings = telegram_settings
    mqtt.set_profile_callbacks(_set_profile_enabled_sync)
    if mqtt_settings.enabled:
        mqtt.connect(mqtt_settings)
    else:
        mqtt.disconnect()
    telegram.configure(telegram_settings)


async def start_notifiers() -> None:
    await http_notifier.start()
    await nvr_notifier.start()
    if _telegram_settings and _telegram_settings.enabled:
        await telegram.start()


async def stop_notifiers() -> None:
    mqtt.disconnect()
    await telegram.stop()
    await http_notifier.stop()
    await nvr_notifier.stop()


class ActionRunError(Exception):
    def __init__(self, message: str, detail: Optional[dict] = None):
        super().__init__(message)
        self.detail = detail


async def run_scheduled_action(
    action: ScheduledAction,
    profile: Profile,
    *,
    mqtt_settings: Optional[MqttSettings] = None,
    telegram_settings: Optional[TelegramSettings] = None,
) -> dict[str, Any]:
    channel = (action.channel or "").strip().lower()
    folder = folder_for_profile(profile)
    result = dummy_inference_result(profile)
    output_root = ""
    source_for_templates: Optional[str] = None

    notif = parse_notification(channel, action.notification_config or {})
    test_notif = replace(notif, enabled=True)

    ms = mqtt_settings or _mqtt_settings
    ts = telegram_settings or _telegram_settings

    loop = asyncio.get_event_loop()

    if channel == "mqtt":
        if not ms or not ms.enabled:
            raise ActionRunError("MQTT is not enabled")
        if getattr(mqtt, "_connected", False) is not True:
            raise ActionRunError("MQTT client is not connected")
        if not (getattr(test_notif, "topic", "") or "").strip():
            raise ActionRunError("MQTT topic is empty")
        await loop.run_in_executor(
            _notify_executor,
            functools.partial(
                mqtt.publish_notification,
                test_notif,
                result,
                folder,
                output_root,
                source_for_templates,
            ),
        )
    elif channel == "telegram":
        if not ts or not ts.enabled or not (ts.token or "").strip():
            raise ActionRunError("Telegram is not enabled or token is empty")
        if not (getattr(test_notif, "chatId", "") or "").strip():
            raise ActionRunError("Telegram chat ID is empty")
        await telegram.send_notification(
            test_notif, result, folder, output_root, source_for_templates,
        )
    elif channel == "http":
        if not (getattr(test_notif, "url", "") or "").strip():
            raise ActionRunError("HTTP notification URL is empty")
        await http_notifier.send_notification(
            test_notif, result, folder, output_root, source_for_templates,
        )
    elif channel == "nvr":
        if not (getattr(test_notif, "baseUrl", "") or "").strip():
            raise ActionRunError("NVR base URL is empty")
        await nvr_notifier.send_notification(
            test_notif,
            folder,
            result=result,
            output_root=output_root,
            source_image_path=source_for_templates,
        )
    elif channel == "script":
        if not (getattr(test_notif, "scriptPath", "") or "").strip():
            raise ActionRunError("Script path is empty")
        await loop.run_in_executor(
            _notify_executor,
            functools.partial(
                script_notifier.run_notification,
                test_notif,
                result,
                folder,
                output_root,
                source_for_templates,
            ),
        )
    elif channel == "evalex":
        if not (getattr(test_notif, "serverAddress", "") or "").strip():
            raise ActionRunError("Evalex server address is empty")
        if not getattr(test_notif, "cameraIds", []):
            raise ActionRunError("Evalex camera IDs list is empty")
        result_dict = await send_evalex_notification(test_notif, result, logger)
        if result_dict.get("status") == "error":
            # Surface top-level error if set, otherwise use first error from list
            error_msg = result_dict.get("error") or (result_dict.get("errors") or ["Evalex failed"])[0]
            raise ActionRunError(f"Evalex error: {error_msg}", detail=result_dict)
        return result_dict
    else:
        raise ActionRunError(f"Unknown channel: {channel}")

    return {"status": "ok", "message": "Notification sent", "channel": channel}
