"""PiyoAI-compatible notification settings types (vendored for TaskPlanner; no piyoai import)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .. import APP_DIR

__all__ = [
    "APP_DIR",
    "EvalexBackupNotification",
    "EvalexCameraNotification",
    "FolderConfig",
    "HttpHeaderEntry",
    "HttpNotification",
    "MqttNotification",
    "MqttSettings",
    "NvrNotification",
    "ScriptNotification",
    "TelegramNotification",
    "TelegramSettings",
    "_parse_bool_setting",
    "_parse_http_notifications",
    "_parse_nvr_notifications",
]


def _parse_bool_setting(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return default


@dataclass
class MqttSettings:
    broker: str = ""
    port: int = 1883
    username: str = ""
    password: str = ""
    publishQos: int = 1
    subscribeQos: int = 1
    enabled: bool = False
    listenerEnabled: bool = False
    listenerTopicPrefix: str = "piyoai/listen"
    commandListenerEnabled: bool = False
    commandListenerTopicPrefix: str = "piyoai/command"
    profileListenerEnabled: bool = False
    profileListenerTopicPrefix: str = "taskplanner/profile"


@dataclass
class TelegramSettings:
    token: str = ""
    enabled: bool = False
    botEnabled: bool = False
    botAllowedChatIds: list = field(default_factory=list)
    botCommands: list = field(default_factory=list)
    botBlacklistPatterns: list = field(default_factory=list)


@dataclass
class MqttNotification:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    enabled: bool = True
    topic: str = ""
    payload: Literal["json", "image", "both"] = "json"
    messageMode: Literal["raw", "template", "simple"] = "raw"
    jsonFields: list = field(default_factory=list)
    template: str = ""
    omitCorrelationIdFromTopic: bool = False


@dataclass
class TelegramNotification:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    enabled: bool = True
    chatId: str = ""
    payload: Literal["json", "image", "both"] = "json"
    messageMode: Literal["raw", "template", "simple"] = "raw"
    jsonFields: list = field(default_factory=list)
    template: str = ""


@dataclass
class HttpHeaderEntry:
    name: str = ""
    value: str = ""


@dataclass
class HttpNotification:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    enabled: bool = True
    url: str = ""
    getQueryTemplate: str = ""
    method: Literal["GET", "POST", "PUT"] = "POST"
    payload: Literal["json", "image", "both"] = "json"
    messageMode: Literal["raw", "template", "simple"] = "raw"
    jsonFields: list = field(default_factory=list)
    template: str = ""
    authType: Literal["none", "basic", "digest", "bearer"] = "none"
    httpUsername: str = ""
    httpPassword: str = ""
    httpBearerToken: str = ""
    httpExtraHeaders: list = field(default_factory=list)
    httpBodyEncoding: Literal["json", "raw"] = "json"
    httpContentType: str = "text/plain; charset=utf-8"


@dataclass
class ScriptNotification:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    enabled: bool = True
    scriptPath: str = ""
    argumentTemplates: list = field(default_factory=list)
    timeoutSeconds: int = 120


@dataclass
class NvrNotification:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    enabled: bool = True
    brand: Literal["dahua", "ezviz", "hikvision", "reolink", "blueiris"] = "reolink"
    baseUrl: str = ""
    httpUsername: str = ""
    httpPassword: str = ""
    verifySsl: bool = True
    channel: int = 0
    reolinkUseV20Api: bool = False
    hikvisionTrackId: int = 0
    blueIrisCameraShortName: str = ""
    blueIrisMemoTemplate: str = ""


@dataclass
class EvalexCameraNotification:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    enabled: bool = True
    app: Literal["vizmux", "piyoai", "vizrec"] = "vizmux"
    serverAddress: str = ""
    cameraIds: list = field(default_factory=list)
    action: Literal["enable", "disable"] = "enable"


@dataclass
class EvalexBackupNotification:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    enabled: bool = True
    app: Literal["vizmux", "piyoai", "vizrec"] = "vizmux"
    serverAddress: str = ""
    retentionDays: int = 7


@dataclass
class FolderConfig:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    enabled: bool = True
    friendlyName: str = ""
    watchPath: str = ""
    storeOutput: bool = False
    filePrefix: str = ""
    mqttNotifications: list = field(default_factory=list)
    telegramNotifications: list = field(default_factory=list)
    httpNotifications: list = field(default_factory=list)
    scriptNotifications: list = field(default_factory=list)
    nvrNotifications: list = field(default_factory=list)


def _parse_http_notifications(items: list) -> list:
    result = []
    for entry in items:
        obj = HttpNotification()
        for k, v in entry.items():
            if k == "httpExtraHeaders" and isinstance(v, list):
                headers = []
                for h in v:
                    if isinstance(h, dict):
                        headers.append(HttpHeaderEntry(
                            name=str(h.get("name", "") or ""),
                            value=str(h.get("value", "") or ""),
                        ))
                    elif isinstance(h, HttpHeaderEntry):
                        headers.append(h)
                obj.httpExtraHeaders = headers
            elif hasattr(obj, k):
                setattr(obj, k, v)
        result.append(obj)
    return result


def _parse_nvr_notifications(items: list) -> list:
    result = []
    for entry in items:
        obj = NvrNotification()
        for k, v in entry.items():
            if not hasattr(obj, k):
                continue
            if k == "channel":
                try:
                    obj.channel = int(v)
                except (TypeError, ValueError):
                    obj.channel = 0
            elif k == "hikvisionTrackId":
                try:
                    obj.hikvisionTrackId = int(v)
                except (TypeError, ValueError):
                    obj.hikvisionTrackId = 0
            elif k in ("verifySsl", "reolinkUseV20Api", "enabled"):
                if isinstance(v, bool):
                    setattr(obj, k, v)
                elif isinstance(v, str):
                    setattr(obj, k, v.strip().lower() in ("1", "true", "yes"))
                else:
                    setattr(obj, k, bool(v))
            elif k == "blueIrisMemoTemplate":
                obj.blueIrisMemoTemplate = "" if v is None else str(v)
            elif k == "blueIrisCameraShortName":
                obj.blueIrisCameraShortName = "" if v is None else str(v)
            else:
                setattr(obj, k, v)
        result.append(obj)
    return result
