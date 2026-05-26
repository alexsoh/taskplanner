from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from tp.main import app


def test_create_profile_defaults_to_disabled():
    client = TestClient(app)

    created = client.post("/api/profiles", json={"name": "New"}).json()
    assert created["enabled"] is False
    assert created["run_latest_per_channel_on_activation"] is False


def test_update_profile_run_latest_on_activation():
    client = TestClient(app)

    created = client.post("/api/profiles", json={"name": "Home"}).json()
    updated = client.patch(
        f"/api/profiles/{created['id']}",
        json={"run_latest_per_channel_on_activation": True},
    ).json()
    assert updated["run_latest_per_channel_on_activation"] is True


def test_create_profile_enabled_triggers_activation_catchup():
    client = TestClient(app)

    with patch("tp.main.dispatch_profile_activation_catchup") as catchup:
        created = client.post(
            "/api/profiles",
            json={"name": "Active", "enabled": True},
        ).json()
        catchup.assert_called_once_with(created["id"])


def test_create_profile_disables_other_profiles():
    client = TestClient(app)

    first = client.post("/api/profiles", json={"name": "First", "enabled": True}).json()
    second = client.post("/api/profiles", json={"name": "Second", "enabled": True}).json()

    profiles = {p["id"]: p for p in client.get("/api/profiles").json()}
    assert profiles[first["id"]]["enabled"] is False
    assert profiles[second["id"]]["enabled"] is True


def test_update_profile_enabling_disables_others():
    client = TestClient(app)

    first = client.post("/api/profiles", json={"name": "First", "enabled": True}).json()
    second = client.post("/api/profiles", json={"name": "Second"}).json()
    client.patch(f"/api/profiles/{second['id']}", json={"enabled": True})

    profiles = {p["id"]: p for p in client.get("/api/profiles").json()}
    assert profiles[first["id"]]["enabled"] is False
    assert profiles[second["id"]]["enabled"] is True


def test_copy_profile_defaults_to_disabled():
    client = TestClient(app)

    source = client.post("/api/profiles", json={"name": "Active", "enabled": True}).json()
    copied = client.post(f"/api/profiles/{source['id']}/copy", json={"name": "Copy"}).json()

    profiles = {p["id"]: p for p in client.get("/api/profiles").json()}
    assert profiles[source["id"]]["enabled"] is True
    assert profiles[copied["id"]]["enabled"] is False


def test_create_profile_disabled_leaves_others_enabled():
    client = TestClient(app)

    first = client.post("/api/profiles", json={"name": "First", "enabled": True}).json()
    second = client.post("/api/profiles", json={"name": "Second", "enabled": False}).json()

    profiles = {p["id"]: p for p in client.get("/api/profiles").json()}
    assert profiles[first["id"]]["enabled"] is True
    assert profiles[second["id"]]["enabled"] is False
