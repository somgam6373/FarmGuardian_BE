from typing import Annotated

import pytest
from fastapi import Depends
from sqlalchemy import text

from app.core.auth import current_user, get_owned_field, get_owned_zone
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


NOT_FOUND = {"error": {"code": "NOT_FOUND", "message": "찾을 수 없습니다"}}


@app.get("/_test/fields/{field_id}", dependencies=[Depends(get_owned_field)])
def _field(field_id: int):
    return {"field_id": field_id}


@app.get("/_test/zones/{zone_id}")
def _zone(zone_id: Annotated[int, Depends(get_owned_zone)]):
    return {"zone_id": zone_id}


def _as(uid):
    return {"X-User-Id": str(uid)}


def test_owner_reads_own_field_and_zone(client, make_user, make_field, make_zone):
    uid = make_user("owner")
    fid = make_field(uid)
    zid = make_zone(fid, uid)

    assert client.get(f"/_test/fields/{fid}", headers=_as(uid)).json() == {"field_id": fid}
    assert client.get(f"/_test/zones/{zid}", headers=_as(uid)).json() == {"zone_id": zid}


def test_other_users_resources_look_like_missing_ones(client, make_user, make_field, make_zone):
    owner, other = make_user("owner"), make_user("other")
    fid = make_field(owner)
    zid = make_zone(fid, owner)

    for path in (f"/_test/fields/{fid}", f"/_test/zones/{zid}"):
        r = client.get(path, headers=_as(other))

        assert (r.status_code, r.json()) == (404, NOT_FOUND)
    assert client.get("/_test/fields/123456789", headers=_as(other)).json() == NOT_FOUND


def test_missing_header_beats_not_found(client):
    r = client.get("/_test/fields/123456789")

    assert (r.status_code, r.json()) == (401, UNAUTHORIZED)


@pytest.mark.parametrize("rid", [0, -1, 10**20])
def test_out_of_range_ids_are_404(client, make_user, rid):
    uid = make_user("owner")

    for path in (f"/_test/fields/{rid}", f"/_test/zones/{rid}"):
        r = client.get(path, headers=_as(uid))

        assert (r.status_code, r.json()) == (404, NOT_FOUND)


def test_non_integer_id_is_validation_error(client, make_user):
    r = client.get("/_test/fields/abc", headers=_as(make_user("owner")))

    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
