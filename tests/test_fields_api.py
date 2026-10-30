import pytest

from app.catalog.application import catalog_service
from tests.farm_support import install_fake_farmmap, judge

FIELD_KEYS = {"id", "name", "area_m2", "geometry", "bbox", "zones"}


@pytest.fixture
def fake_farmmap(monkeypatch):
    return install_fake_farmmap(monkeypatch)


def auth(uid):
    return {"X-User-Id": str(uid)}


def create(client, uid, ids, name="앞밭"):
    return client.post(
        "/fields", json={"name": name, "parcel_farmmap_ids": ids}, headers=auth(uid)
    )


@pytest.mark.parametrize(
    "method, path", [("post", "/fields"), ("get", "/fields"), ("delete", "/fields/1")]
)
def test_requires_authentication(client, method, path):
    response = client.request(method, path, json={"name": "f", "parcel_farmmap_ids": ["1"]})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_create_201_and_list(client, make_user, fake_farmmap):
    uid = make_user("farmer")
    response = create(client, uid, ["1", "2"])
    assert response.status_code == 201
    field = response.json()
    assert set(field) == FIELD_KEYS
    assert field["area_m2"] == 200.0 and field["zones"] == []
    assert client.get("/fields", headers=auth(uid)).json() == [field]


@pytest.mark.parametrize(
    "body",
    [
        {"name": "f", "parcel_farmmap_ids": []},
        {"name": "f", "parcel_farmmap_ids": [str(i) for i in range(1, 22)]},
        {"name": "f", "parcel_farmmap_ids": ["1", "1"]},
        {"name": "f", "parcel_farmmap_ids": [""]},
        {"name": "f", "parcel_farmmap_ids": ["12a"]},
        {"name": "f", "parcel_farmmap_ids": ["１２"]},
        {"name": "", "parcel_farmmap_ids": ["1"]},
        {"name": "가" * 31, "parcel_farmmap_ids": ["1"]},
        {"parcel_farmmap_ids": ["1"]},
    ],
)
def test_invalid_body_is_422(client, make_user, fake_farmmap, body):
    response = client.post("/fields", json=body, headers=auth(make_user("farmer")))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert fake_farmmap[0] == []


def test_blank_name_is_422(client, make_user, fake_farmmap):
    assert create(client, make_user("farmer"), ["1"], name="   ").status_code == 422


def test_name_is_stripped(client, make_user, fake_farmmap):
    assert create(client, make_user("farmer"), ["1"], name=" 앞밭 ").json()["name"] == "앞밭"


def test_unknown_id_is_422_not_found(client, make_user, fake_farmmap):
    fake_farmmap[1].add("2")
    response = create(client, make_user("farmer"), ["1", "2"])
    assert response.status_code == 422
    [error] = response.json()["error"]["details"]["errors"]
    assert error["loc"] == ["body", "parcel_farmmap_ids", 1]
    assert error["type"] == "not_found"


def test_used_parcel_is_409(client, make_user, fake_farmmap):
    uid = make_user("farmer")
    create(client, uid, ["1"])
    response = create(client, uid, ["1", "2"])
    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "PARCEL_ALREADY_USED",
        "message": "이미 다른 밭에 등록된 필지입니다",
        "details": {"farmmap_ids": ["1"]},
    }


def test_other_users_parcel_is_fine(client, make_user, fake_farmmap):
    create(client, make_user("me"), ["1"])
    assert create(client, make_user("other"), ["1"]).status_code == 201


def test_upstream_error_is_502(client, make_user, fake_farmmap):
    uid = make_user("farmer")
    fake_farmmap[2].add("1")
    response = create(client, uid, ["1"])
    assert response.status_code == 502
    assert response.json()["error"]["details"] == {"source": "farmmap"}
    assert client.get("/fields", headers=auth(uid)).json() == []


def test_delete_204_and_404s(client, make_user, make_field, fake_farmmap):
    me, other = make_user("me"), make_user("other")
    field_id = create(client, me, ["1"]).json()["id"]
    others = make_field(other)
    assert client.delete(f"/fields/{others}", headers=auth(me)).status_code == 404
    assert client.delete("/fields/999999999", headers=auth(me)).status_code == 404
    response = client.delete(f"/fields/{field_id}", headers=auth(me))
    assert response.status_code == 204 and response.content == b""
    assert client.get("/fields", headers=auth(me)).json() == []


def test_deleted_field_frees_parcels(client, make_user, fake_farmmap):
    uid = make_user("farmer")
    field_id = create(client, uid, ["1"]).json()["id"]
    client.delete(f"/fields/{field_id}", headers=auth(uid))
    assert create(client, uid, ["1"]).status_code == 201


def test_list_shows_zone_summary(client, make_user, make_zone, fake_farmmap):
    uid = make_user("farmer")
    field_id = create(client, uid, ["1"]).json()["id"]
    zone_id = make_zone(field_id, uid)
    [field] = client.get("/fields", headers=auth(uid)).json()
    [zone] = field["zones"]
    assert zone["id"] == zone_id
    assert zone["crop"] == {"id": 1, "name": "감자"}
    assert zone["last_spray"] is None and zone["last_judgment"] is None


def test_list_shows_last_judgment(client, db, make_user, make_zone, fake_farmmap):
    uid = make_user("farmer")
    field_id = create(client, uid, ["1", "2"]).json()["id"]
    judged, stale = make_zone(field_id, uid), make_zone(field_id, uid)
    judge(db, judged, catalog_service.list_pesticides(1)[0].pesticide.id, "OK")
    judge(db, stale, 99999999, "OK")  # 카탈로그에 없는 약제는 건너뛴다
    zones = client.get("/fields", headers=auth(uid)).json()[0]["zones"]
    assert zones[0]["last_judgment"]["created_at"].endswith("+09:00")
    assert zones[1]["last_judgment"] is None
