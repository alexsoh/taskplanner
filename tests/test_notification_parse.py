from __future__ import annotations

from tp.notification_parse import parse_notification


def test_parse_evalex_notification_normalizes_camera_ids():
    notif = parse_notification(
        "evalex",
        {
            "app": "vizmux",
            "serverAddress": "http://localhost:8000",
            "cameraIds": [" cam-1 ", "", "cam-2"],
            "action": "enable",
        },
    )
    assert notif.cameraIds == ["cam-1", "cam-2"]


def test_parse_evalex_notification_accepts_single_camera_id():
    notif = parse_notification(
        "evalex",
        {
            "serverAddress": "http://localhost:8000",
            "cameraIds": "cam-1",
        },
    )
    assert notif.cameraIds == ["cam-1"]
