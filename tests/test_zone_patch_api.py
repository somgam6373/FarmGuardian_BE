from datetime import timedelta

import pytest

from app.core.time import today_kst

ZONE_KEYS = {
    "id", "field_id", "name", "crop", "planted_at", "history_confirmed", "area_m2", "geometry",
    "bbox",
}


def auth(uid):
    return {"X-User-Id": str(uid)}


@pytest.fixture
def zone(make_user, make_field, make_zone):
    uid = make_user("farmer")
    return uid, make_zone(make_field(uid), uid)


def patch(client, uid, zone_id, body):
    return client.patch(f"/zones/{zone_id}", json=body, headers=auth(uid))


def test_requires_authentication(client, zone):
    assert client.patch(f"/zones/{zone[1]}", json={}).status_code == 401


def test_other_users_zone_is_404_even_with_bad_body(client, zone, make_user):
    assert patch(client, make_user("other"), zone[1], {"name": None}).status_code == 404


def test_empty_body_is_unchanged(client, zone):
    response = patch(client, *zone, {})
    assert response.status_code == 200
    assert set(response.json()) == ZONE_KEYS
    assert response.json()["name"] == "z"


def test_rename_and_set_date(client, zone):
    day = today_kst().isoformat()
    body = patch(client, *zone, {"name": " 앞쪽 ", "planted_at": day}).json()
    assert body["name"] == "앞쪽" and body["planted_at"] == day


def test_null_date_clears_it(client, zone):
    patch(client, *zone, {"planted_at": today_kst().isoformat(), "history_confirmed": True})
    body = patch(client, *zone, {"planted_at": None}).json()
    assert body["planted_at"] is None and body["history_confirmed"] is False


@pytest.mark.parametrize(
    "body",
    [
        {"name": None},
        {"crop_id": None},
        {"history_confirmed": None},
        {"name": "   "},
        {"name": "가" * 31},
        {"crop_id": 999},
        {"planted_at": "tomorrow"},
    ],
)
def test_invalid_body_is_422(client, zone, body):
    if body.get("planted_at") == "tomorrow":
        body = {"planted_at": (today_kst() + timedelta(days=1)).isoformat()}
    response = patch(client, *zone, body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("field", ["name", "crop_id", "history_confirmed"])
def test_null_points_at_the_field(client, zone, field):
    response = patch(client, *zone, {field: None})
    [error] = response.json()["error"]["details"]["errors"]
    assert error["loc"] == ["body", field]
