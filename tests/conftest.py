import os
from pathlib import Path

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

# app.core.config가 import 시점에 Settings()를 만들므로 app보다 먼저 설정한다.
# DB 테스트가 개발 DB를 건드리지 않도록 DATABASE_URL을 항상 테스트 DB로 덮어쓴다.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or dotenv_values(
    Path(__file__).resolve().parents[1] / ".env"
).get("TEST_DATABASE_URL")
os.environ["DATABASE_URL"] = (
    TEST_DATABASE_URL or "postgresql+psycopg://test:test@localhost:5432/test"
)
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("FARMMAP_API_KEY", "test-farmmap-key")

_SQUARE = "ST_GeomFromText('MULTIPOLYGON(((0 0,10 0,10 10,0 10,0 0)))', 5179)"


@pytest.fixture
def db():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set")
    from app.core.db import engine

    assert engine.url.database.endswith("_test"), "refusing to run on a non-test database"
    # 바깥 트랜잭션을 테스트가 끝나면 롤백한다. 앱 코드의 commit()은 savepoint만 해제한다.
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db):
    from app.core.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def make_user(db):
    def make(username: str) -> int:
        return db.scalar(
            text("INSERT INTO users (username, password_hash) VALUES (:u, 'x') RETURNING id"),
            {"u": username},
        )

    return make


@pytest.fixture
def make_field(db):
    def make(user_id: int) -> int:
        return db.scalar(
            text(
                "INSERT INTO field (user_id, name, geom) "
                f"VALUES (:u, 'f', {_SQUARE}) RETURNING id"
            ),
            {"u": user_id},
        )

    return make


@pytest.fixture
def make_zone(db):
    def make(field_id: int, user_id: int) -> int:
        return db.scalar(
            text(
                "INSERT INTO zone (field_id, user_id, name, crop_id, geom) "
                f"VALUES (:f, :u, 'z', (SELECT min(id) FROM crop), {_SQUARE}) RETURNING id"
            ),
            {"f": field_id, "u": user_id},
        )

    return make
