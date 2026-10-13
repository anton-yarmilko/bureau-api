import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db import Base, get_session, make_engine
from app.main import app

TEST_KEY = "test-key"
# CI sets TEST_DATABASE_URL to a real Postgres; locally the suite uses in-memory SQLite.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite://")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", TEST_KEY)
    get_settings.cache_clear()
    if TEST_DATABASE_URL.startswith("sqlite"):
        engine = make_engine(TEST_DATABASE_URL, poolclass=StaticPool)
    else:
        engine = make_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        with TestSession() as session:
            yield session

    app.dependency_overrides[get_session] = override
    with TestClient(app, headers={"X-API-Key": TEST_KEY}) as c:
        yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()
    engine.dispose()


@pytest.fixture
def make_players(client):
    def _make(*names: str) -> list[str]:
        return [client.post("/players", json={"display_name": n}).json()["id"] for n in names]

    return _make
