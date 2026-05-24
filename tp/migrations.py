"""Database migrations for TaskPlanner."""

from sqlalchemy import text
from sqlalchemy.orm import Session


def _column_exists(db: Session, table: str, column: str) -> bool:
    rows = db.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


def migrate_add_upgrade_columns(db: Session) -> None:
    """Add upgrade_token and evalex_base columns to app_settings table if they don't exist."""
    if _column_exists(db, "app_settings", "upgrade_token"):
        return
    try:
        db.execute(text("ALTER TABLE app_settings ADD COLUMN upgrade_token VARCHAR(255)"))
        db.execute(text(
            "ALTER TABLE app_settings ADD COLUMN evalex_base VARCHAR(255) DEFAULT 'https://evalex.duckdns.org'"
        ))
        db.commit()
    except Exception:
        db.rollback()
        raise


def migrate_add_ip_whitelist_and_port(db: Session) -> None:
    """Add allowed_ips_json and server_port columns to app_settings table if they don't exist."""
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
        raise


def migrate_add_profile_color(db: Session) -> None:
    """Add color column to profiles table if it doesn't exist (pre-v0.1.27 DBs)."""
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
        raise
