from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from tp.calendar import expand_calendar
from tp.migrations import (
    migrate_add_profile_color,
    migrate_add_profile_run_latest_on_activation,
    migrate_days_of_week_to_array,
)


def test_migrate_add_profile_color_backfills_legacy_db(tmp_path: Path) -> None:
    dbpath = tmp_path / "legacy.db"
    engine = create_engine(
        f"sqlite:///{dbpath}",
        connect_args={"check_same_thread": False},
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                """CREATE TABLE profiles (
                    id VARCHAR(36) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME
                )"""
            )
        )
        conn.execute(
            text(
                """CREATE TABLE scheduled_actions (
                    id VARCHAR(36) PRIMARY KEY,
                    profile_id VARCHAR(36) NOT NULL,
                    label VARCHAR(255) NOT NULL,
                    day_of_week INTEGER NOT NULL,
                    time VARCHAR(5) NOT NULL,
                    channel VARCHAR(16) NOT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    notification_config JSON NOT NULL
                )"""
            )
        )
        conn.execute(
            text(
                "INSERT INTO profiles VALUES ('p1', 'Home', 'UTC', 1, NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO scheduled_actions VALUES "
                "('a1', 'p1', 'Morning', 0, '09:00', 'mqtt', 1, '{}')"
            )
        )

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        # Must run migration before expand_calendar to add days_of_week column
        migrate_days_of_week_to_array(db)
        migrate_add_profile_color(db)
        migrate_add_profile_run_latest_on_activation(db)
        events = expand_calendar(db, date(2026, 5, 18), date(2026, 5, 24))
        assert len(events) == 1
        assert events[0].profile_color == "#38bdf8"
    finally:
        db.close()


def test_migrate_days_of_week_to_array(tmp_path: Path) -> None:
    """Test migration from day_of_week int to days_of_week JSON array."""
    import json
    
    dbpath = tmp_path / "legacy_days.db"
    engine = create_engine(
        f"sqlite:///{dbpath}",
        connect_args={"check_same_thread": False},
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                """CREATE TABLE profiles (
                    id VARCHAR(36) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME
                )"""
            )
        )
        conn.execute(
            text(
                """CREATE TABLE scheduled_actions (
                    id VARCHAR(36) PRIMARY KEY,
                    profile_id VARCHAR(36) NOT NULL,
                    label VARCHAR(255) NOT NULL,
                    day_of_week INTEGER NOT NULL,
                    time VARCHAR(5) NOT NULL,
                    channel VARCHAR(16) NOT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    notification_config JSON NOT NULL
                )"""
            )
        )
        conn.execute(text("INSERT INTO profiles VALUES ('p1', 'Home', 'UTC', 1, NULL)"))
        conn.execute(
            text(
                "INSERT INTO scheduled_actions VALUES "
                "('a1', 'p1', 'Morning', 0, '09:00', 'mqtt', 1, '{}')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO scheduled_actions VALUES "
                "('a2', 'p1', 'Evening', 2, '18:00', 'mqtt', 1, '{}')"
            )
        )

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        migrate_days_of_week_to_array(db)
        
        # Verify the migration: check that days_of_week column exists and has been backfilled
        result = db.execute(
            text("SELECT id, days_of_week FROM scheduled_actions ORDER BY id")
        ).fetchall()
        
        assert len(result) == 2
        # a1 had day_of_week=0, should become [0]
        # SQLite returns JSON as string, need to parse
        days_a1 = json.loads(result[0][1]) if isinstance(result[0][1], str) else result[0][1]
        assert days_a1 == [0], f"Expected [0], got {days_a1}"
        # a2 had day_of_week=2, should become [2]
        days_a2 = json.loads(result[1][1]) if isinstance(result[1][1], str) else result[1][1]
        assert days_a2 == [2], f"Expected [2], got {days_a2}"
    finally:
        db.close()
