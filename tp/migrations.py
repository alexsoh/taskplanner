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
