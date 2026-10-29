from sqlalchemy import text

from app.seed_demo import ensure_dev_user


def test_creates_the_locked_dev_user(db):
    uid = ensure_dev_user(db)

    row = db.execute(
        text("SELECT username, password_hash FROM users WHERE id = :i"), {"i": uid}
    ).one()

    assert tuple(row) == ("dev", "!")


def test_is_idempotent(db):
    first, second = ensure_dev_user(db), ensure_dev_user(db)

    assert first == second
    assert db.scalar(text("SELECT count(*) FROM users WHERE username = 'dev'")) == 1
