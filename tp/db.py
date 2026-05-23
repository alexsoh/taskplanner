from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from . import APP_DIR
from .models import Base

import os

DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
if os.environ.get("TASKPLANNER_TEST_DB") == "memory":
    DATABASE_URL = "sqlite:///:memory:"
else:
    DATABASE_URL = f"sqlite:///{DATA_DIR / 'taskplanner.db'}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    # Run migrations
    from .migrations import migrate_add_upgrade_columns, migrate_add_ip_whitelist_and_port
    db = SessionLocal()
    try:
        migrate_add_upgrade_columns(db)
        migrate_add_ip_whitelist_and_port(db)
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
