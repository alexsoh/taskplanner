"""Database migrations for TaskPlanner."""

import logging

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

