from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

from sqlalchemy.orm import Session

from .models import AppSettingsRow
from .notify.settings_types import MqttSettings, TelegramSettings


def _default_mqtt() -> dict[str, Any]:
    return asdict(MqttSettings())


def _default_telegram() -> dict[str, Any]:
    d = asdict(TelegramSettings())
    d["botEnabled"] = False
    return d


def _mqtt_from_dict(d: dict[str, Any]) -> MqttSettings:
    obj = MqttSettings()
    for k, v in d.items():
        if hasattr(obj, k):
            setattr(obj, k, v)
    return obj


def _telegram_from_dict(d: dict[str, Any]) -> TelegramSettings:
    obj = TelegramSettings()
    for k, v in d.items():
        if hasattr(obj, k):
            setattr(obj, k, v)
    return obj


def get_or_create_settings(db: Session) -> AppSettingsRow:
    row = db.get(AppSettingsRow, 1)
    if row is None:
        row = AppSettingsRow(id=1, mqtt_json=_default_mqtt(), telegram_json=_default_telegram())
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def load_mqtt_telegram(db: Session) -> tuple[MqttSettings, TelegramSettings]:
    row = get_or_create_settings(db)
    return _mqtt_from_dict(row.mqtt_json or {}), _telegram_from_dict(row.telegram_json or {})


def settings_to_api(db: Session) -> dict[str, Any]:
    row = get_or_create_settings(db)
    return {"mqtt": row.mqtt_json or _default_mqtt(), "telegram": row.telegram_json or _default_telegram()}


def update_settings(
    db: Session,
    mqtt: Optional[dict],
    telegram: Optional[dict],
) -> dict[str, Any]:
    row = get_or_create_settings(db)
    if mqtt is not None:
        merged = {**_default_mqtt(), **(row.mqtt_json or {}), **mqtt}
        row.mqtt_json = merged
    if telegram is not None:
        merged = {**_default_telegram(), **(row.telegram_json or {}), **telegram}
        row.telegram_json = merged
    db.commit()
    db.refresh(row)
    return settings_to_api(db)
