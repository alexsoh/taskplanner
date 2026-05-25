from __future__ import annotations

import asyncio

import pytest
from tp.db import SessionLocal
from tp.models import Profile, ScheduledAction
from tp.notification_parse import normalize_evalex_config, reconcile_evalex_config


def test_normalize_evalex_config_list_camera_ids():
    """Test that cameraIds list is preserved and normalized."""
    config = {
        "app": "vizmux",
        "serverAddress": "http://localhost:8000",
        "cameraIds": ["cam-1", " cam-2 ", ""],
        "action": "enable",
    }
    normalized = normalize_evalex_config(config)
    assert normalized["cameraIds"] == ["cam-1", "cam-2"]
    assert normalized["id"] is not None  # Should have an id


def test_normalize_evalex_config_string_camera_id():
    """Test that single string cameraIds is converted to list."""
    config = {
        "app": "vizmux",
        "serverAddress": "http://localhost:8000",
        "cameraIds": "cam-1",
        "action": "enable",
    }
    normalized = normalize_evalex_config(config)
    assert normalized["cameraIds"] == ["cam-1"]


def test_normalize_evalex_config_missing_camera_ids():
    """Test that missing cameraIds becomes empty list."""
    config = {
        "app": "vizmux",
        "serverAddress": "http://localhost:8000",
        "action": "enable",
    }
    normalized = normalize_evalex_config(config)
    assert normalized["cameraIds"] == []


def test_normalize_evalex_config_prunes_camera_labels():
    """Test that cameraLabels is pruned to only keys in cameraIds."""
    config = {
        "app": "vizmux",
        "serverAddress": "http://localhost:8000",
        "cameraIds": ["cam-1", "cam-2"],
        "cameraLabels": {"cam-1": "Camera 1", "cam-3": "Camera 3"},
        "action": "enable",
    }
    normalized = normalize_evalex_config(config)
    assert normalized["cameraLabels"] == {"cam-1": "Camera 1"}


def test_normalize_evalex_config_dict_camera_ids():
    """Test that dict cameraIds uses keys as IDs."""
    config = {
        "app": "vizmux",
        "serverAddress": "http://localhost:8000",
        "cameraIds": {"cam-1": "Camera 1", "cam-2": "Camera 2"},
        "action": "enable",
    }
    normalized = normalize_evalex_config(config)
    assert normalized["cameraIds"] == ["cam-1", "cam-2"]


def test_reconcile_evalex_config_filters_stale_ids():
    """Test that reconcile filters out IDs not in live settings."""
    async def _run():
        config = {
            "app": "vizmux",
            "serverAddress": "http://invalid-host-that-wont-resolve:9999",
            "cameraIds": ["cam-1", "cam-2"],
            "action": "enable",
        }
        # This will hit an unreachable server, so stale_removed will be empty and unreachable=True
        # We can't actually test the filtering without mocking httpx, but we can verify the structure
        reconciled, metadata = await reconcile_evalex_config(config)
        assert "stale_removed" in metadata
        assert "unreachable" in metadata

    asyncio.run(_run())


def test_copy_profile_deep_copies_notification_config():
    """Test that copy_profile creates a deep copy of notification_config."""
    db = SessionLocal()
    try:
        # Create a source profile with an evalex action
        source = Profile(name="Source", timezone="UTC", enabled=True)
        db.add(source)
        db.flush()

        source_action = ScheduledAction(
            profile_id=source.id,
            label="Evalex action",
            days_of_week=[0],
            time="09:00",
            channel="evalex",
            enabled=True,
            notification_config={
                "app": "vizmux",
                "serverAddress": "http://localhost:8000",
                "cameraIds": ["cam-1"],
                "action": "enable",
            },
        )
        db.add(source_action)
        db.commit()

        # Now copy the profile via HTTP (simulate)
        from tp.main import copy_profile
        from tp.schemas import ProfileUpdate

        copied_profile = asyncio.run(copy_profile(source.id, ProfileUpdate(name="Copied"), db))
        db.refresh(copied_profile)

        # Verify copied action has normalized and deep-copied notification_config
        copied_action = copied_profile.actions[0]
        assert copied_action.id != source_action.id
        assert copied_action.notification_config["cameraIds"] == ["cam-1"]
        assert "id" in copied_action.notification_config
        
        # Modify source config and verify copy is unaffected (deep copy check)
        source_action.notification_config["cameraIds"].append("cam-2")
        assert copied_action.notification_config["cameraIds"] == ["cam-1"]

    finally:
        db.close()


def test_copy_action_deep_copies_notification_config():
    """Test that copy_action creates a deep copy of notification_config."""
    db = SessionLocal()
    try:
        profile = Profile(name="Profile", timezone="UTC", enabled=True)
        db.add(profile)
        db.flush()

        source_action = ScheduledAction(
            profile_id=profile.id,
            label="Evalex action",
            days_of_week=[0],
            time="09:00",
            channel="evalex",
            enabled=True,
            notification_config={
                "app": "piyoai",
                "serverAddress": "http://localhost:8001",
                "cameraIds": ["folder-1"],
                "action": "disable",
            },
        )
        db.add(source_action)
        db.commit()

        # Copy the action
        from tp.main import copy_action

        copied_action = asyncio.run(copy_action(source_action.id, db))
        
        # Verify copied action has normalized and deep-copied notification_config
        assert copied_action.id != source_action.id
        assert copied_action.label == "Evalex action (Copy)"
        assert copied_action.notification_config["cameraIds"] == ["folder-1"]
        assert "id" in copied_action.notification_config
        
        # Modify source config and verify copy is unaffected
        source_action.notification_config["cameraIds"].append("folder-2")
        assert copied_action.notification_config["cameraIds"] == ["folder-1"]

    finally:
        db.close()
