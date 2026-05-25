from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["TASKPLANNER_TEST_DB"] = "memory"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from tp import db as db_module
from tp.db import engine
from tp.models import Base


@pytest.fixture(autouse=True)
def fresh_db():
    db_module._migrations_applied = False
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    db_module._migrations_applied = False
