from __future__ import annotations

from tp.notification_parse import (
    normalize_evalex_backup_config,
    normalize_evalex_camera_config,
    parse_notification,
)


def test_parse_evalex_camera_notification_normalizes_camera_ids():
    notif = parse_notification(
        "evalex-camera",
        {
            "app": "vizmux",
            "serverAddress": "http://localhost:8000",
            "cameraIds": [" cam-1 ", "", "cam-2"],
            "action": "enable",
        },
    )
    assert notif.cameraIds == ["cam-1", "cam-2"]


def test_parse_evalex_camera_notification_accepts_single_camera_id():
    notif = parse_notification(
        "evalex-camera",
        {
            "serverAddress": "http://localhost:8000",
            "cameraIds": "cam-1",
        },
    )
    assert notif.cameraIds == ["cam-1"]


def test_parse_evalex_backup_notification_coerces_retention_days():
    notif = parse_notification(
        "evalex-backup",
        {
            "app": "vizrec",
            "serverAddress": "http://localhost:8002",
            "retentionDays": "14",
        },
    )
    assert notif.retentionDays == 14


def test_parse_evalex_backup_notification_defaults_invalid_retention():
    notif = parse_notification(
        "evalex-backup",
        {
            "serverAddress": "http://localhost:8002",
            "retentionDays": "invalid",
        },
    )
    assert notif.retentionDays == 7


def test_normalize_evalex_backup_config_clamps_retention():
    normalized = normalize_evalex_backup_config({"retentionDays": 0})
    assert normalized["retentionDays"] == 1

    normalized = normalize_evalex_backup_config({})
    assert normalized["retentionDays"] == 7
    assert normalized["id"] is not None


def test_normalize_evalex_camera_config_list_camera_ids():
    config = {
        "app": "vizmux",
        "serverAddress": "http://localhost:8000",
        "cameraIds": ["cam-1", " cam-2 ", ""],
        "action": "enable",
    }
    normalized = normalize_evalex_camera_config(config)
    assert normalized["cameraIds"] == ["cam-1", "cam-2"]
    assert normalized["id"] is not None
