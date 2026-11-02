from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.catalog.application import catalog_service
from app.core.auth import current_user, get_owned_zone
from app.core.db import get_db
from app.core.errors import AppError
from app.core.time import today_kst
from app.farm.application import zone_reader
from app.farm.application.zone_reader import ZoneContext
from app.judgment.application import service
from app.main import app
from app.spraying.application import spray_service
from tests.judgment_scenarios import (
    PLANTED,
    TODAY,
    assess,
    counting_selection,
    pests_with_drugs,
    pool,
)

PEST = pests_with_drugs(1)[0]
DETAIL_KEYS = {"id", "name", "item_name", "moa", "company", "form", "ingredients", "kind"}
ITEM_KEYS = {"pesticide", "at_planting_only", "result"}
RESULT_KEYS = {"pesticide_id", "moa", "verdict", "checks", "notices", "data_asof"}


def auth(uid):
    return {"X-User-Id": str(uid)}


def preview(client, uid, zone, **params):
    return client.get(f"/zones/{zone}/judgments/preview", params=params, headers=auth(uid))


@pytest.fixture
def farm(make_user, make_field, make_zone):
    uid = make_user("farmer")
    return uid, make_zone(make_field(uid), uid)


@pytest.fixture
def no_db(monkeypatch):
    """구역·이력 읽기만 DB를 쓴다. 두 호출을 대신해 서비스와 라우트를 DB 없이 돌린다."""
    monkeypatch.setattr(
        zone_reader, "get_zone_context", lambda db, zone_id: ZoneContext(1, PLANTED, True)
    )
    monkeypatch.setattr(spray_service, "history", lambda db, zone_id: [])


# --- DB 없이 도는 테스트 ---------------------------------------------------------------


def test_service_follows_the_pool_order_and_matches_assess(no_db):
    items = service.preview(None, 1, pest_id=PEST, apply_date=TODAY, today=TODAY)

    assert [i.entry for i in items] == catalog_service.list_pesticides(1, PEST)
    for item in items[:3]:
        drug_id = item.entry.pesticide.id
        assert item.result == assess(pesticide_id=drug_id, pest_id=PEST).result


def test_service_rejects_a_pest_of_another_crop_and_an_unknown_pest(no_db):
    for pest_id in (pests_with_drugs(2)[0], 999999):
        with pytest.raises(AppError) as info:
            service.preview(None, 1, pest_id=pest_id, apply_date=None, today=TODAY)

        assert (info.value.status, info.value.code) == (404, "NOT_FOUND")


def test_service_apply_date_limit_names_the_query_parameter(no_db):
    with pytest.raises(AppError) as info:
        service.preview(None, 1, pest_id=PEST, apply_date=date(2101, 1, 1), today=TODAY)

    assert info.value.status == 422
    assert info.value.details["errors"][0]["loc"] == ["query", "apply_date"]
    last_day = service.preview(None, 1, pest_id=PEST, apply_date=date(2100, 12, 31), today=TODAY)
    assert last_day


def test_route_shape_and_gzip_without_a_database(no_db):
    overrides = {current_user: lambda: 1, get_owned_zone: lambda: 1, get_db: lambda: None}
    app.dependency_overrides.update(overrides)
    try:
        r = TestClient(app).get(
            "/zones/1/judgments/preview",
            params={"pest_id": PEST, "apply_date": TODAY.isoformat()},
            headers={"Accept-Encoding": "gzip"},
        )
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)
    body = r.json()

    assert r.status_code == 200 and r.headers["content-encoding"] == "gzip"
    assert [i["pesticide"]["id"] for i in body] == [d.id for d in pool(1, PEST)]
    assert all(set(i) == ITEM_KEYS for i in body)
    assert all(set(i["pesticide"]) == DETAIL_KEYS for i in body)
    assert all(set(i["result"]) == RESULT_KEYS for i in body)
    assert all(isinstance(i["at_planting_only"], bool) for i in body)


# --- DB가 있어야 도는 테스트 -------------------------------------------------------------


def test_requires_authentication(client):
    r = client.get("/zones/1/judgments/preview", params={"pest_id": 1})

    assert (r.status_code, r.json()["error"]["code"]) == (401, "UNAUTHORIZED")


def test_foreign_and_unknown_zones_are_404(client, make_user, make_field, make_zone, farm):
    uid, _ = farm
    other = make_user("other")
    foreign = make_zone(make_field(other), other)
    for zone in (foreign, 999999):
        r = preview(client, uid, zone)  # pest_id가 없어도 404가 422보다 먼저다

        assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_missing_pest_id_is_422(client, farm):
    r = preview(client, *farm)

    assert r.status_code == 422
    assert r.json()["error"]["details"]["errors"][0]["loc"] == ["query", "pest_id"]


@pytest.mark.parametrize("pest_id", [999999, pests_with_drugs(2)[0]], ids=["unknown", "other-crop"])
def test_unknown_pest_or_another_crops_pest_is_404(client, farm, pest_id):
    r = preview(client, *farm, pest_id=pest_id)

    assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_apply_date_after_2100_is_422(client, farm):
    r = preview(client, *farm, pest_id=PEST, apply_date="2101-01-01")

    assert r.status_code == 422
    assert r.json()["error"]["details"]["errors"][0]["loc"] == ["query", "apply_date"]
    assert preview(client, *farm, pest_id=PEST, apply_date="2100-12-31").status_code == 200


def test_items_follow_the_pool_order_and_carry_a_full_result(client, farm):
    body = preview(client, *farm, pest_id=PEST).json()

    assert [i["pesticide"]["id"] for i in body] == [d.id for d in pool(1, PEST)]
    assert all(set(i) == ITEM_KEYS for i in body)
    assert all(set(i["result"]) == RESULT_KEYS for i in body)


def test_each_result_equals_the_one_a_judgment_would_give(client, db, farm):
    uid, zone = farm
    db.execute(
        text("UPDATE zone SET planted_at = :p, history_confirmed = true WHERE id = :id"),
        {"p": PLANTED, "id": zone},
    )
    day = TODAY.isoformat()
    body = preview(client, uid, zone, pest_id=PEST, apply_date=day).json()

    for item in body[:3]:
        posted = client.post(
            f"/zones/{zone}/judgments",
            json={"pesticide_id": item["pesticide"]["id"], "pest_id": PEST, "apply_date": day},
            headers=auth(uid),
        )
        assert posted.json()["result"] == item["result"]


def test_preview_stores_nothing(client, db, farm):
    uid, zone = farm
    count = text("SELECT count(*) FROM judgment WHERE zone_id = :z")
    before = db.scalar(count, {"z": zone})

    assert preview(client, uid, zone, pest_id=PEST).status_code == 200
    assert db.scalar(count, {"z": zone}) == before


def test_zone_harvest_at_feeds_the_preview_items(client, db, farm):
    uid, zone = farm
    pest_id, drug = counting_selection()
    db.execute(
        text("UPDATE zone SET planted_at = :p, history_confirmed = true WHERE id = :id"),
        {"p": PLANTED, "id": zone},
    )
    harvest_at = today_kst() + timedelta(days=400)
    db.execute(
        text("UPDATE zone SET harvest_at = :d WHERE id = :id"), {"d": harvest_at, "id": zone}
    )

    body = preview(client, uid, zone, pest_id=pest_id).json()

    item = next(i for i in body if i["pesticide"]["id"] == drug.id)
    check = next(c for c in item["result"]["checks"] if c["key"] == "timing")
    assert check["facts"]["harvest_at"] == harvest_at.isoformat()
    assert check["facts"]["margin_days"] == 400 - check["facts"]["phi_days"]
