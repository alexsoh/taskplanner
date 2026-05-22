from __future__ import annotations

from typing import Any, TypeVar

from .notify.settings_types import (
    EvalexNotification,
    HttpNotification,
    MqttNotification,
    NvrNotification,
    ScriptNotification,
    TelegramNotification,
    _parse_http_notifications,
    _parse_nvr_notifications,
)

T = TypeVar("T")
CHANNEL_TYPES = {
    "mqtt": MqttNotification,
    "telegram": TelegramNotification,
    "http": HttpNotification,
    "script": ScriptNotification,
    "nvr": NvrNotification,
    "evalex": EvalexNotification,
}


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
    obj = cls()
    for k, v in (config or {}).items():
        if hasattr(obj, k):
            setattr(obj, k, v)
    return obj
