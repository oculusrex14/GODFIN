from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

# The API lifespan uses the production SessionLocal by design. Unit tests
# explicitly disable it so they never seed, migrate, or decrypt the user's
# real database.
os.environ["GODFIN_TESTING"] = "1"
os.environ["DB_PATH"] = "/tmp/godfin_pytest_unused.db"
os.environ["ENCRYPTION_KEY"] = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="

from app.core.database import Base, get_db
from app.models import *  # noqa: F401, F403
from app.seed import run_seeds


# Use a file-based temp DB shared via named connection so the same DB
# is visible across threads (TestClient runs endpoints in a worker thread).
TEST_DB_URL = "sqlite:///file:testdb?mode=memory&cache=shared&uri=true"


@pytest.fixture
def db_engine():
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    TestSession = sessionmaker(bind=db_engine)
    session = TestSession()
    run_seeds(session)
    yield session
    session.close()


@pytest.fixture
def client(db_engine, db_session):
    TestSession = sessionmaker(bind=db_engine)

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    # Import app here to avoid lifespan running against production DB
    from app.main import app

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth_client(client):
    """Client with PIN set and authenticated."""
    from app.core.auth import _active_tokens
    _active_tokens.clear()

    resp = client.post("/api/v1/auth/set-pin", json={"pin": "1234"})
    assert resp.status_code == 200, f"set-pin failed: {resp.text}"
    resp = client.post("/api/v1/auth/verify-pin", json={"pin": "1234"})
    assert resp.status_code == 200, f"verify-pin failed: {resp.text}"
    token = resp.json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client
