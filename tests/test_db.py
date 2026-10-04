from sqlalchemy.orm import Session

from app.core.db import get_db


def test_get_db_gives_a_new_session_per_call():
    first, second = get_db(), get_db()

    a, b = next(first), next(second)

    assert isinstance(a, Session)
    assert a is not b
    first.close()
    second.close()
