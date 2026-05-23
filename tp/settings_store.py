from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

from sqlalchemy.orm import Session

from .models import AppSettingsRow
from .notify.settings_types import MqttSettings, TelegramSettings
from .ip_filter import validate_ip_or_cidr


def _default_mqtt() -> dict[str, Any]:
    return asdict(MqttSettings())


def _default_telegram() -> dict[str, Any]:
    d = asdict(TelegramSettings())
    d["botEnabled"] = False
    return d


def _default_allowed_ips() -> dict[str, Any]:
    """Default allowed IPs - restrict to localhost."""
    return {"allowedIps": ["127.0.0.1", "::1"]}


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
    allowed_ips_data = row.allowed_ips_json or _default_allowed_ips()
    return {
        "mqtt": row.mqtt_json or _default_mqtt(),
        "telegram": row.telegram_json or _default_telegram(),
        "upgradeToken": row.upgrade_token,
        "allowedIps": allowed_ips_data.get("allowedIps", ["127.0.0.1", "::1"]),
        "serverPort": row.server_port or 8200,
    }


def get_evalex_base(db: Session) -> str:
    """Get the Evalex base URL from settings."""
    row = get_or_create_settings(db)
    return row.evalex_base or "https://evalex.duckdns.org"


def get_allowed_ips(db: Session) -> list[str]:
    """Get the list of allowed IPs from settings."""
    row = get_or_create_settings(db)
    allowed_ips_data = row.allowed_ips_json or _default_allowed_ips()
    return allowed_ips_data.get("allowedIps", ["127.0.0.1", "::1"])


def get_server_port(db: Session) -> int:
    """Get the server port from settings."""
    row = get_or_create_settings(db)
    return row.server_port or 8200


def update_settings(
    db: Session,
    mqtt: Optional[dict],
    telegram: Optional[dict],
    upgrade_token: Optional[str] = None,
    evalex_base: Optional[str] = None,
    allowed_ips: Optional[list[str]] = None,
    server_port: Optional[int] = None,
) -> dict[str, Any]:
    row = get_or_create_settings(db)
    if mqtt is not None:
        merged = {**_default_mqtt(), **(row.mqtt_json or {}), **mqtt}
        row.mqtt_json = merged
    if telegram is not None:
        merged = {**_default_telegram(), **(row.telegram_json or {}), **telegram}
        row.telegram_json = merged
    
    # Handle upgrade token: prevent accidental clearing if already set
    if upgrade_token is not None:
        if upgrade_token == "":
            # Reject empty string if token is already set (prevent accidental loss)
            if row.upgrade_token:
                raise ValueError("Cannot clear upgrade token; omit the field to keep existing value")
        else:
            # Set non-empty token
            row.upgrade_token = upgrade_token
    
    # Handle evalex base
    if evalex_base is not None:
        row.evalex_base = evalex_base
    
    # Handle allowed IPs
    if allowed_ips is not None:
        # Always ensure loopback addresses are included (cannot be removed)
        loopback_ips = {"127.0.0.1", "::1"}
        provided_ips = set(allowed_ips)
        merged_ips = list(loopback_ips | provided_ips)
        
        # Validate all IPs/CIDRs
        for ip_str in merged_ips:
            if not validate_ip_or_cidr(ip_str):
                raise ValueError(f"Invalid IP address or CIDR range: {ip_str}")
        row.allowed_ips_json = {"allowedIps": merged_ips}
    
    # Handle server port
    if server_port is not None:
        if not (1 <= server_port <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got {server_port}")
        row.server_port = server_port
    
    db.commit()
    db.refresh(row)
    return settings_to_api(db)
