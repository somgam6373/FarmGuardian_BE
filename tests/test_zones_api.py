import pytest

from app.farm.infrastructure import field_repository
from tests.farm_support import square

SPLIT = {"direction": "crosswise", "ratios": [1, 1]}
ZONES = [{"name": "앞", "crop_id": 1}, {"name": "뒤", "crop_id": 2, "planted_at": "2026-03-01"}]


def auth(uid):
    return {"X-User-Id": str(uid)}


@pytest.fixture
def farm(db, make_user):
    uid = make_user("farmer")
    # 20×10 밭 (정사각형 필지 2개)
    return uid, field_repository.insert_field(db, uid, "f", [square("1"), square("2", 10)])


def preview(client, uid, field_id, body=SPLIT):
    return client.post(f"/fields/{field_id}/split-preview", json=body, headers=auth(uid))


def create(client, uid, field_id, zones=ZONES, split=SPLIT):
    body = {**split, "zones": zones}
    return client.post(f"/fields/{field_id}/zones", json=body, headers=auth(uid))


@pytest.mark.parametrize("path", ["split-preview", "zones"])
def test_requires_authentication(client, farm, path):
    response = client.post(f"/fields/{farm[1]}/{path}", json={**SPLIT, "zones": ZONES})
    assert response.status_code == 401


def test_preview_200_shape(client, farm):
    response = preview(client, *farm)
    assert response.status_code == 200
    pieces = response.json()
    assert [set(p) for p in pieces] == [{"geometry", "area_m2"}] * 2
    assert [p["area_m2"] for p in pieces] == [100.0, 100.0]


@pytest.mark.parametrize("path", ["split-preview", "zones"])
@pytest.mark.parametrize(
    "split",
    [
        {"direction": "diagonal", "ratios": [1, 1]},
        {"direction": "crosswise", "ratios": []},
        {"direction": "crosswise", "ratios": [1] * 11},
        {"direction": "crosswise", "ratios": [0, 1]},
        {"direction": "crosswise", "ratios": [-1, 1]},
        {"direction": "crosswise", "ratios": [1.5, 1]},
        {"direction": "crosswise", "ratios": [101, 1]},
        {"ratios": [1, 1]},
    ],
)
def test_invalid_split_is_422(client, farm, path, split):
    uid, field_id = farm
    response = client.post(
        f"/fields/{field_id}/{path}", json={**split, "zones": ZONES}, headers=auth(uid)
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "zones",
    [
        ZONES[:1],
        [{"name": "", "crop_id": 1}, ZONES[1]],
        [{"name": "   ", "crop_id": 1}, ZONES[1]],
        [{"name": "가" * 31, "crop_id": 1}, ZONES[1]],
        [{"name": "앞"}, ZONES[1]],
    ],
)
def test_invalid_zones_is_422(client, farm, zones):
    assert create(client, *farm, zones=zones).status_code == 422


def test_unknown_crop_is_422(client, farm):
    response = create(client, *farm, zones=[ZONES[0], {"name": "뒤", "crop_id": 999}])
    assert response.status_code == 422
    [error] = response.json()["error"]["details"]["errors"]
    assert error["loc"] == ["body", "zones", 1, "crop_id"] and error["type"] == "not_found"


@pytest.mark.parametrize("path", ["split-preview", "zones"])
def test_other_users_field_is_404_even_with_bad_body(client, farm, make_user, path):
    other = make_user("other")
    response = client.post(f"/fields/{farm[1]}/{path}", json={"ratios": []}, headers=auth(other))
    assert response.status_code == 404


def test_create_201_then_409(client, farm):
    response = create(client, *farm)
    assert response.status_code == 201
    zones = response.json()
    assert [z["name"] for z in zones] == ["앞", "뒤"]
    assert zones[1]["planted_at"] == "2026-03-01"
    assert zones[0]["bbox"] == [0.0, 0.0, 10.0, 10.0]
    again = create(client, *farm)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "FIELD_ALREADY_SPLIT"


def test_create_matches_preview(client, farm):
    pieces = preview(client, *farm).json()
    zones = create(client, *farm).json()
    assert [z["geometry"] for z in zones] == [p["geometry"] for p in pieces]


def test_preview_allowed_after_split(client, farm):
    create(client, *farm)
    assert preview(client, *farm).status_code == 200


def test_get_fields_shows_zones(client, farm):
    uid, field_id = farm
    zones = create(client, *farm).json()
    [field] = client.get("/fields", headers=auth(uid)).json()
    assert [z["id"] for z in field["zones"]] == [z["id"] for z in zones]
    assert field["zones"][1]["crop"] == {"id": 2, "name": "배추"}
