from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from tp.db import SessionLocal
from tp.main import app
from tp.models import ExecutionRun, Profile
from tp.tzutil import format_server_local


client = TestClient(app)


def test_list_executions_includes_local_time_fields():
    db = SessionLocal()
    try:
        p = Profile(name="H", timezone="UTC", enabled=True)
        db.add(p)
        db.flush()
        fired = datetime(2026, 5, 18, 9, 30, tzinfo=timezone.utc)
        scheduled = datetime(2026, 5, 18, 9, 0, tzinfo=timezone.utc)
        db.add(
            ExecutionRun(
                profile_id=p.id,
                scheduled_for=scheduled,
                fired_at=fired,
                status="failed",
                error="test error",
                channel="http",
                label="Test",
            )
        )
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/executions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    row = data[0]
    assert row["status"] == "failed"
    assert row["error"] == "test error"
    assert row["fired_at_local"] == format_server_local(fired)
    assert row["scheduled_for_local"] == format_server_local(scheduled)
    assert "T" not in row["fired_at_local"] or row["fired_at_local"].count("-") >= 2


def test_health_includes_server_timezone():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "server_timezone" in body
    assert body["server_timezone"]


def test_server_info_endpoint():
    resp = client.get("/api/server-info")
    assert resp.status_code == 200
    assert resp.json()["server_timezone"]
