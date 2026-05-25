"""Database migrations for TaskPlanner."""

import logging
import sqlite3

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("taskplanner.migrations")


def _table_exists(db: Session, table: str) -> bool:
    row = db.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table},
    ).first()
    return row is not None


def _column_exists(db: Session, table: str, column: str) -> bool:
    if not _table_exists(db, table):
        return False
    rows = db.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


def migrate_add_upgrade_columns(db: Session) -> None:
    """Add upgrade_token and evalex_base columns to app_settings table if they don't exist."""
    if not _table_exists(db, "app_settings"):
        return
    needs_token = not _column_exists(db, "app_settings", "upgrade_token")
    needs_base = not _column_exists(db, "app_settings", "evalex_base")
    if not needs_token and not needs_base:
        return
    try:
        if needs_token:
            db.execute(text("ALTER TABLE app_settings ADD COLUMN upgrade_token VARCHAR(255)"))
        if needs_base:
            db.execute(text(
                "ALTER TABLE app_settings ADD COLUMN evalex_base VARCHAR(255) DEFAULT 'https://evalex.duckdns.org'"
            ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("migrate_add_upgrade_columns failed")
        raise


def migrate_add_ip_whitelist_and_port(db: Session) -> None:
    """Add allowed_ips_json and server_port columns to app_settings table if they don't exist."""
    if not _table_exists(db, "app_settings"):
        return
    needs_ips = not _column_exists(db, "app_settings", "allowed_ips_json")
    needs_port = not _column_exists(db, "app_settings", "server_port")
    if not needs_ips and not needs_port:
        return
    try:
        if needs_ips:
            db.execute(text("ALTER TABLE app_settings ADD COLUMN allowed_ips_json JSON DEFAULT '{\"allowedIps\": [\"127.0.0.1\", \"::1\"]}'"))
        if needs_port:
            db.execute(text("ALTER TABLE app_settings ADD COLUMN server_port INTEGER DEFAULT 8200"))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("migrate_add_ip_whitelist_and_port failed")
        raise


def migrate_add_profile_color(db: Session) -> None:
    """Add color column to profiles table if it doesn't exist (pre-v0.1.27 DBs)."""
    if not _table_exists(db, "profiles"):
        return
    if _column_exists(db, "profiles", "color"):
        db.execute(text("UPDATE profiles SET color = '#38bdf8' WHERE color IS NULL OR color = ''"))
        db.commit()
        return
    try:
        db.execute(text("ALTER TABLE profiles ADD COLUMN color VARCHAR(16) DEFAULT '#38bdf8'"))
        db.execute(text("UPDATE profiles SET color = '#38bdf8' WHERE color IS NULL OR color = ''"))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("migrate_add_profile_color failed")
        raise


def migrate_days_of_week_to_array(db: Session) -> None:
    """Convert day_of_week int to days_of_week JSON array (multi-day support)."""
    if not _table_exists(db, "scheduled_actions"):
        return
    if _column_exists(db, "scheduled_actions", "days_of_week"):
        # Already migrated; skip
        return
    if not _column_exists(db, "scheduled_actions", "day_of_week"):
        # No old column; shouldn't happen but skip
        return
    try:
        db.execute(text("ALTER TABLE scheduled_actions ADD COLUMN days_of_week JSON"))
        db.execute(text("UPDATE scheduled_actions SET days_of_week = json_array(day_of_week)"))
        # Set days_of_week to [0] for any NULL rows (shouldn't happen, but be safe)
        db.execute(text("UPDATE scheduled_actions SET days_of_week = json('[0]') WHERE days_of_week IS NULL"))
        db.commit()
        logger.info("migrate_days_of_week_to_array completed: day_of_week → days_of_week")
    except Exception:
        db.rollback()
        logger.exception("migrate_days_of_week_to_array failed")
        raise


def migrate_ensure_single_active_profile(db: Session) -> None:
    """If multiple profiles are enabled (legacy bug), keep only the oldest active."""
    if not _table_exists(db, "profiles"):
        return
    rows = db.execute(
        text("SELECT id FROM profiles WHERE enabled = 1 ORDER BY created_at, id"),
    ).fetchall()
    if len(rows) <= 1:
        return
    keeper_id = rows[0][0]
    db.execute(
        text("UPDATE profiles SET enabled = 0 WHERE enabled = 1 AND id != :id"),
        {"id": keeper_id},
    )
    db.commit()
    logger.info(
        "migrate_ensure_single_active_profile: disabled %d extra active profile(s)",
        len(rows) - 1,
    )


def migrate_drop_day_of_week_column(db: Session) -> None:
    """Drop the old day_of_week column now that days_of_week JSON array is in use.

    The previous migration added days_of_week but left day_of_week with a NOT NULL
    constraint and no default, causing every INSERT to fail.  SQLite 3.35+ supports
    ALTER TABLE … DROP COLUMN.
    """
    if not _table_exists(db, "scheduled_actions"):
        return
    if not _column_exists(db, "scheduled_actions", "day_of_week"):
        return  # Already dropped or never existed
    if not _column_exists(db, "scheduled_actions", "days_of_week"):
        return  # days_of_week migration hasn't run yet; let it go first
    try:
        if sqlite3.sqlite_version_info >= (3, 35, 0):
            db.execute(text("ALTER TABLE scheduled_actions DROP COLUMN day_of_week"))
        else:
            # SQLite < 3.35 does not support DROP COLUMN — rebuild the table without it
            db.execute(text("""
                CREATE TABLE scheduled_actions_new (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    profile_id VARCHAR(36) NOT NULL
                        REFERENCES profiles(id) ON DELETE CASCADE,
                    label VARCHAR(255) NOT NULL DEFAULT 'Action',
                    days_of_week JSON NOT NULL DEFAULT '[0]',
                    time VARCHAR(5) NOT NULL,
                    channel VARCHAR(16) NOT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    notification_config JSON NOT NULL DEFAULT '{}'
                )
            """))
            db.execute(text("""
                INSERT INTO scheduled_actions_new
                    (id, profile_id, label, days_of_week, time, channel, enabled, notification_config)
                SELECT id, profile_id, label, days_of_week, time, channel, enabled, notification_config
                FROM scheduled_actions
            """))
            db.execute(text("DROP TABLE scheduled_actions"))
            db.execute(text("ALTER TABLE scheduled_actions_new RENAME TO scheduled_actions"))
        db.commit()
        logger.info("migrate_drop_day_of_week_column completed: dropped day_of_week column")
    except Exception:
        db.rollback()
        logger.exception("migrate_drop_day_of_week_column failed")
        raise

