import uuid
from datetime import timedelta

import pytest

from app.catalog.application import catalog_service as catalog
from app.core.time import today_kst

SPRAY_KEYS = {"id", "pesticide", "sprayed_on", "source"}
PESTICIDE_KEYS = {"id", "name", "item_name", "moa"}
DRUGS = [e.pesticide for e in catalog.list_pesticides(1)]
WITH_MOA = next(d for d in DRUGS if d.moa)
WITHOUT_MOA = next(d for d in DRUGS if d.moa is None)


def auth(uid):
    return {"X-User-Id": str(uid)}


@pytest.fixture
def farm(make_user, make_field, make_zone):
    uid = make_user("farmer")
    return uid, make_zone(make_field(uid), uid)


def save(client, uid, zone, pesticide_id=WITH_MOA.id, **kw):
    body = {"pesticide_id": pesticide_id, "source": "manual", "request_id": str(uuid.uuid4())}
    return client.post(f"/zones/{zone}/sprays", json={**body, **kw}, headers=auth(uid))


def listing(client, uid, zone, **params):
    return client.get(f"/zones/{zone}/sprays", params=params, headers=auth(uid))


@pytest.mark.parametrize(
    "method,path",
    [("post", "/zones/1/sprays"), ("get", "/zones/1/sprays"), ("delete", "/zones/1/sprays/1")],
)
def test_requires_authentication(client, method, path):
    r = client.request(method, path, json={} if method == "post" else None)

    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_foreign_and_unknown_zones_are_404(client, make_user, make_field, make_zone, farm):
    uid, _ = farm
    other = make_user("other")
    foreign = make_zone(make_field(other), other)
    for zone in (foreign, 999999):
        responses = [
            client.post(f"/zones/{zone}/sprays", json={}, headers=auth(uid)),  # 404 beats 422
            listing(client, uid, zone),
            client.delete(f"/zones/{zone}/sprays/1", headers=auth(uid)),
        ]

        assert [(r.status_code, r.json()["error"]["code"]) for r in responses] == [
            (404, "NOT_FOUND")
        ] * 3


def test_post_creates_and_returns_the_spray(client, farm):
    uid, zone = farm
    r = save(client, uid, zone, sprayed_on="2026-01-05", source="app")
    body = r.json()

    assert r.status_code == 201
    assert set(body) == SPRAY_KEYS and set(body["pesticide"]) == PESTICIDE_KEYS
    assert (body["sprayed_on"], body["source"]) == ("2026-01-05", "app")
    assert body["pesticide"]["id"] == WITH_MOA.id
    assert body["pesticide"]["name"] == WITH_MOA.name
    assert body["pesticide"]["item_name"] == WITH_MOA.item_name
    assert body["pesticide"]["moa"] == {
        "label_kr": WITH_MOA.moa.label_kr,
        "system": WITH_MOA.moa.system,
        "code": WITH_MOA.moa.code,
    }


def test_pesticide_without_moa_has_null_moa(client, farm):
    uid, zone = farm

    assert save(client, uid, zone, WITHOUT_MOA.id).json()["pesticide"]["moa"] is None


def test_omitted_date_is_today_kst(client, farm):
    uid, zone = farm

    assert save(client, uid, zone).json()["sprayed_on"] == today_kst().isoformat()


def test_future_date_is_422_and_today_is_accepted(client, farm):
    uid, zone = farm
    tomorrow = (today_kst() + timedelta(days=1)).isoformat()
    r = save(client, uid, zone, sprayed_on=tomorrow)
    error = r.json()["error"]

    assert (r.status_code, error["code"]) == (422, "VALIDATION_ERROR")
    assert error["details"]["errors"][0]["loc"] == ["body", "sprayed_on"]
    assert tomorrow not in str(error)
    assert save(client, uid, zone, sprayed_on=today_kst().isoformat()).status_code == 201
    assert listing(client, uid, zone).json()["total"] == 1


@pytest.mark.parametrize(
    "patch,field",
    [
        ({"pesticide_id": 999999}, "pesticide_id"),
        ({"pesticide_id": "abc"}, "pesticide_id"),
        ({"source": "robot"}, "source"),
        ({"request_id": "not-a-uuid"}, "request_id"),
        ({"sprayed_on": "2026-13-45"}, "sprayed_on"),
    ],
)
def test_invalid_values_are_422_with_their_location(client, farm, patch, field):
    uid, zone = farm
    r = save(client, uid, zone, **patch)
    error = r.json()["error"]

    assert (r.status_code, error["code"]) == (422, "VALIDATION_ERROR")
    assert error["details"]["errors"][0]["loc"] == ["body", field]


@pytest.mark.parametrize("field", ["pesticide_id", "source", "request_id"])
def test_missing_required_field_is_422(client, farm, field):
    uid, zone = farm
    body = {"pesticide_id": WITH_MOA.id, "source": "manual", "request_id": str(uuid.uuid4())}
    del body[field]
    r = client.post(f"/zones/{zone}/sprays", json=body, headers=auth(uid))

    assert r.status_code == 422
    assert r.json()["error"]["details"]["errors"][0]["loc"] == ["body", field]


def test_retry_with_the_same_request_id_returns_200_and_stores_once(client, farm):
    uid, zone = farm
    rid = str(uuid.uuid4())
    first = save(client, uid, zone, request_id=rid)
    again = save(client, uid, zone, request_id=rid)

    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json() == first.json()
    assert listing(client, uid, zone).json()["total"] == 1


def test_request_id_of_another_zone_or_user_is_422_without_a_record(
    client, make_user, make_field, make_zone, farm
):
    uid, zone = farm
    rid = str(uuid.uuid4())
    save(client, uid, zone, request_id=rid)
    other = make_user("other")
    targets = [(uid, make_zone(make_field(uid), uid)), (other, make_zone(make_field(other), other))]
    for user, target in targets:
        r = save(client, user, target, request_id=rid)
        error = r.json()["error"]

        assert (r.status_code, error["code"]) == (422, "VALIDATION_ERROR")
        assert error["details"]["errors"][0]["loc"] == ["body", "request_id"]
        assert listing(client, user, target).json() == {"total": 0, "items": []}


def test_duplicate_is_409_with_the_existing_spray(client, farm):
    uid, zone = farm
    first = save(client, uid, zone, sprayed_on="2026-01-05")
    r = save(client, uid, zone, sprayed_on="2026-01-05")
    error = r.json()["error"]

    assert (r.status_code, error["code"]) == (409, "DUPLICATE_SPRAY")
    assert error["details"] == {"existing": first.json()}
    assert listing(client, uid, zone).json()["total"] == 1


def test_resending_the_409_request_id_with_allow_duplicate_saves(client, farm):
    uid, zone = farm
    rid = str(uuid.uuid4())
    save(client, uid, zone, sprayed_on="2026-01-05")

    assert save(client, uid, zone, sprayed_on="2026-01-05", request_id=rid).status_code == 409
    r = save(client, uid, zone, sprayed_on="2026-01-05", request_id=rid, allow_duplicate=True)

    assert r.status_code == 201
    assert listing(client, uid, zone).json()["total"] == 2


def test_list_shape_order_and_paging(client, farm):
    uid, zone = farm
    ids = [save(client, uid, zone, sprayed_on=f"2026-01-0{d}").json()["id"] for d in (1, 2, 3, 4)]
    page = listing(client, uid, zone, limit=2, offset=1).json()

    assert set(page) == {"total", "items"} and page["total"] == 4
    assert [s["id"] for s in page["items"]] == [ids[2], ids[1]]
    assert all(set(s) == SPRAY_KEYS for s in page["items"])
    assert [s["id"] for s in listing(client, uid, zone).json()["items"]] == ids[::-1]


def test_empty_history(client, farm):
    uid, zone = farm

    assert listing(client, uid, zone).json() == {"total": 0, "items": []}


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"limit": "x"}])
def test_list_bounds_are_422(client, farm, params):
    uid, zone = farm
    r = listing(client, uid, zone, **params)

    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")


def test_limit_100_is_accepted(client, farm):
    uid, zone = farm

    assert listing(client, uid, zone, limit=100).status_code == 200


def test_cancel_returns_204_and_removes_the_spray(client, farm):
    uid, zone = farm
    spray = save(client, uid, zone).json()
    r = client.delete(f"/zones/{zone}/sprays/{spray['id']}", headers=auth(uid))

    assert (r.status_code, r.content) == (204, b"")
    assert listing(client, uid, zone).json()["total"] == 0
    again = client.delete(f"/zones/{zone}/sprays/{spray['id']}", headers=auth(uid))
    assert (again.status_code, again.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_cancel_of_another_zones_spray_is_404(client, make_field, make_zone, farm):
    uid, zone = farm
    zone2 = make_zone(make_field(uid), uid)
    spray = save(client, uid, zone2).json()
    r = client.delete(f"/zones/{zone}/sprays/{spray['id']}", headers=auth(uid))

    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")
    assert listing(client, uid, zone2).json()["total"] == 1


def test_non_integer_spray_id_is_422(client, farm):
    uid, zone = farm
    r = client.delete(f"/zones/{zone}/sprays/abc", headers=auth(uid))

    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
