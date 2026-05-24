from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from tp.calendar import expand_calendar
from tp.migrations import migrate_add_profile_color


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
        migrate_add_profile_color(db)
        events = expand_calendar(db, date(2026, 5, 18), date(2026, 5, 24))
        assert len(events) == 1
        assert events[0].profile_color == "#38bdf8"
    finally:
        db.close()
