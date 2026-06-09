from __future__ import annotations

import threading
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from . import APP_DIR
from .models import Base

import os

DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
if os.environ.get("TASKPLANNER_TEST_DB") == "memory":
    DATABASE_URL = "sqlite:///:memory:"
    _engine_kwargs = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
else:
    DATABASE_URL = f"sqlite:///{DATA_DIR / 'taskplanner.db'}"
    _engine_kwargs = {"connect_args": {"check_same_thread": False}}

engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_migration_lock = threading.Lock()
_migrations_applied = False


def run_migrations(db: Session) -> None:
    from .migrations import (
        migrate_add_execution_run_unique_index,
        migrate_add_ip_whitelist_and_port,
        migrate_add_profile_color,
        migrate_add_profile_run_latest_on_activation,
        migrate_add_upgrade_columns,
        migrate_days_of_week_to_array,
        migrate_drop_day_of_week_column,
        migrate_ensure_single_active_profile,
        migrate_rename_evalex_channel,
    )

    migrate_add_upgrade_columns(db)
    migrate_add_ip_whitelist_and_port(db)
    migrate_add_profile_color(db)
    migrate_add_profile_run_latest_on_activation(db)
    migrate_days_of_week_to_array(db)
    migrate_drop_day_of_week_column(db)
    migrate_ensure_single_active_profile(db)
    migrate_add_execution_run_unique_index(db)
    migrate_rename_evalex_channel(db)


def ensure_migrations(db: Session) -> None:
    global _migrations_applied
    if _migrations_applied:
        return
    with _migration_lock:
        if _migrations_applied:
            return
        Base.metadata.create_all(bind=engine)
        run_migrations(db)
        _migrations_applied = True


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        run_migrations(db)
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        ensure_migrations(db)
        yield db
    finally:
        db.close()
