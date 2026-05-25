from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from tp.migrations import migrate_ensure_single_active_profile


def test_migrate_ensure_single_active_profile(tmp_path: Path) -> None:
    dbpath = tmp_path / "multi_active.db"
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
                    color VARCHAR(16) NOT NULL DEFAULT '#38bdf8',
                    created_at DATETIME
                )"""
            )
        )
        conn.execute(
            text(
                "INSERT INTO profiles VALUES "
                "('p1', 'First', 'UTC', 1, '#38bdf8', '2020-01-01'), "
                "('p2', 'Second', 'UTC', 1, '#38bdf8', '2021-01-01')"
            )
        )

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        migrate_ensure_single_active_profile(db)
        rows = db.execute(text("SELECT id, enabled FROM profiles ORDER BY id")).fetchall()
        enabled = [r for r in rows if r[1]]
        assert len(enabled) == 1
        assert enabled[0][0] == "p1"
    finally:
        db.close()
