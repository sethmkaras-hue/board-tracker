import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import delete

workspace = TemporaryDirectory()
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", f"sqlite:///{workspace.name}/tests.db")
os.environ.update(APP_ENV="development", DEV_AUTH="1", DEV_PASSWORD="test only")

from tracker.db import Session
from tracker.main import app
from tracker.models import Person, Review


@pytest.fixture(autouse=True)
def migrated_database():
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    yield config
    # This fixture uses disposable data. Empty review rows before the guarded downgrade.
    with Session.begin() as db:
        db.execute(delete(Review))
    command.downgrade(config, "base")


@pytest.fixture
def client():
    with TestClient(app) as test:
        yield test


def login(client, username="engineer", grant=False):
    result = client.post("/api/auth/login", json={"username": username, "password": "test only"})
    assert result.status_code == 200, result.text
    person = result.json()
    client.headers["X-CSRF-Token"] = person["csrf"]
    if grant:
        with Session.begin() as db:
            db.get(Person, person["id"]).admin = True
    return person
