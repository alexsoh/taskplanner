"""Database migrations for TaskPlanner."""

from sqlalchemy import text
from sqlalchemy.orm import Session


def migrate_add_upgrade_columns(db: Session) -> None:
    """Add upgrade_token and evalex_base columns to app_settings table if they don't exist."""
    try:
        # Try to query a non-existent column to check if migration is needed
        db.execute(text("SELECT upgrade_token FROM app_settings LIMIT 1"))
    except Exception:
        # Column doesn't exist, add it
        db.execute(text("ALTER TABLE app_settings ADD COLUMN upgrade_token VARCHAR(255)"))
        db.execute(text(
            "ALTER TABLE app_settings ADD COLUMN evalex_base VARCHAR(255) DEFAULT 'https://evalex.duckdns.org'"
        ))
        db.commit()


def migrate_add_ip_whitelist_and_port(db: Session) -> None:
    """Add allowed_ips_json and server_port columns to app_settings table if they don't exist."""
    try:
        # Try to query the new columns to check if migration is needed
        db.execute(text("SELECT allowed_ips_json, server_port FROM app_settings LIMIT 1"))
    except Exception:
        # Columns don't exist, add them
        db.execute(text("ALTER TABLE app_settings ADD COLUMN allowed_ips_json JSON DEFAULT '{\"allowedIps\": [\"127.0.0.1\", \"::1\"]}'"))
        db.execute(text("ALTER TABLE app_settings ADD COLUMN server_port INTEGER DEFAULT 8200"))
        db.commit()


def migrate_add_profile_color(db: Session) -> None:
    """Add color column to profiles table if it doesn't exist (pre-v0.1.27 DBs)."""
    try:
        db.execute(text("SELECT color FROM profiles LIMIT 1"))
    except Exception:
        db.execute(text("ALTER TABLE profiles ADD COLUMN color VARCHAR(16) DEFAULT '#38bdf8'"))
        db.commit()
