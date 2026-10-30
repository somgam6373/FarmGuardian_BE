import uuid

import pytest
from sqlalchemy import text

from app.catalog.application import catalog_service
from tests.farm_support import judge

ZONE_KEYS = {
    "id", "field_id", "name", "crop", "planted_at", "history_confirmed", "area_m2", "geometry",
    "bbox",
}
WITH_MOA = next(e.pesticide for e in catalog_service.list_pesticides(1) if e.pesticide.moa)


def auth(uid):
    return {"X-User-Id": str(uid)}


@pytest.fixture
def zone(db, make_user, make_field, make_zone):
    uid = make_user("farmer")
    zone_id = make_zone(make_field(uid), uid)
    db.execute(text("UPDATE zone SET planted_at = '2026-05-01' WHERE id = :id"), {"id": zone_id})
    return uid, zone_id


def spray(db, zone_id, day):
    db.execute(
        text(
            "INSERT INTO spray_log (zone_id, pesticide_id, sprayed_on, source, request_id) "
            "VALUES (:z, :p, :d, 'manual', :r)"
        ),
        {"z": zone_id, "p": WITH_MOA.id, "d": day, "r": uuid.uuid4()},
    )


def detail(client, uid, zone_id):
    return client.get(f"/zones/{zone_id}", headers=auth(uid))


def test_requires_authentication(client, zone):
    assert client.get(f"/zones/{zone[1]}").status_code == 401


def test_other_users_and_unknown_zone_are_404(client, zone, make_user):
    assert detail(client, make_user("other"), zone[1]).status_code == 404
    assert detail(client, zone[0], 999999999).status_code == 404


def test_shape_without_history(client, zone):
    response = detail(client, *zone)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == ZONE_KEYS | {"rotation", "recent_judgments"}
    assert body["rotation"] == {"window_start": "2026-05-01", "total": 0, "items": []}
    assert body["recent_judgments"] == []


def test_rotation_counts_sprays(client, db, zone):
    spray(db, zone[1], "2026-06-01")
    spray(db, zone[1], "2026-07-01")
    spray(db, zone[1], "2026-04-01")  # 정식일 이전은 세지 않는다
    rotation = detail(client, *zone).json()["rotation"]
    assert rotation["total"] == 2
    [item] = rotation["items"]
    assert item["count"] == 2
    assert set(item["moa"]) == {"label_kr", "system", "code"}


def test_recent_judgments_newest_five(client, db, zone):
    ids = [
        judge(db, zone[1], WITH_MOA.id, "OK", f"2026-10-0{day}T09:00:00+09:00")
        for day in range(1, 7)
    ]
    judgments = detail(client, *zone).json()["recent_judgments"]
    assert [j["judgment_id"] for j in judgments] == ids[::-1][:5]
    assert judgments[0]["created_at"] == "2026-10-06T09:00:00+09:00"
