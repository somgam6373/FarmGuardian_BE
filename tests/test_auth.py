from typing import Annotated

import pytest
from fastapi import Depends
from sqlalchemy import text

from app.core.auth import current_user
from app.main import app

UNAUTHORIZED = {"error": {"code": "UNAUTHORIZED", "message": "인증이 필요합니다"}}


# 테스트 전용 라우트: 프로덕션 코드에 인증용 경로를 두지 않기 위해 여기서만 등록한다.
@app.get("/_test/me")
def _me(user_id: Annotated[int, Depends(current_user)]):
    return {"user_id": user_id}


def test_valid_header_returns_the_user_id(client, make_user):
    uid = make_user("farmer")

    r = client.get("/_test/me", headers={"X-User-Id": str(uid)})

    assert (r.status_code, r.json()) == (200, {"user_id": uid})


def test_missing_header_is_401(client):
    r = client.get("/_test/me")

    assert (r.status_code, r.json()) == (401, UNAUTHORIZED)


@pytest.mark.parametrize(
    "value", ["", "abc", "0", "-1", "+1", "01", "1.5", "1_0", "1,2", "9" * 19, "١٢".encode()]
)
def test_malformed_header_is_401(client, value):
    r = client.get("/_test/me", headers={"X-User-Id": value})

    assert (r.status_code, r.json()) == (401, UNAUTHORIZED)


def test_withdrawn_or_unknown_user_is_401(client, db, make_user):
    uid = make_user("gone")
    db.execute(text("DELETE FROM users WHERE id = :i"), {"i": uid})

    for value in (str(uid), "9" * 18):
        r = client.get("/_test/me", headers={"X-User-Id": value})

        assert (r.status_code, r.json()) == (401, UNAUTHORIZED)


def test_error_does_not_echo_the_header_value(client):
    r = client.get("/_test/me", headers={"X-User-Id": "secret-value"})

    assert "secret-value" not in r.text
