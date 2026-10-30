import uuid
from datetime import date

from sqlalchemy import text

from app.catalog.application import catalog_service
from app.farm.application import zone_service

SUMMARY_KEYS = {
    "id", "name", "crop", "planted_at", "history_confirmed", "area_m2", "geometry",
    "last_spray", "last_judgment",
}
PESTICIDE_ID = catalog_service.list_pesticides(1)[0].pesticide.id


def spray(db, zone_id, day):
    db.execute(
        text(
            "INSERT INTO spray_log (zone_id, pesticide_id, sprayed_on, source, request_id) "
            "VALUES (:z, :p, :d, 'manual', :r)"
        ),
        {"z": zone_id, "p": PESTICIDE_ID, "d": day, "r": uuid.uuid4()},
    )


def test_summary_shape(db, make_user, make_field, make_zone):
    uid = make_user("farmer")
    field_id = make_field(uid)
    zone_id = make_zone(field_id, uid)
    [summary] = zone_service.summaries(db, [field_id])[field_id]
    assert set(summary) == SUMMARY_KEYS
    assert summary["id"] == zone_id
    assert summary["crop"] == {"id": 1, "name": "감자"}
    assert summary["planted_at"] is None
    assert summary["history_confirmed"] is False
    assert summary["area_m2"] == 100.0
    assert summary["geometry"]["type"] == "MultiPolygon" and "crs" not in summary["geometry"]
    assert summary["last_spray"] is None
    assert summary["last_judgment"] is None


def test_last_spray_is_newest(db, make_user, make_field, make_zone):
    uid = make_user("farmer")
    field_id = make_field(uid)
    zone_id = make_zone(field_id, uid)
    spray(db, zone_id, date(2026, 10, 5))
    spray(db, zone_id, date(2026, 10, 1))
    last = zone_service.summaries(db, [field_id])[field_id][0]["last_spray"]
    assert last["sprayed_on"] == date(2026, 10, 5)
    assert last["source"] == "manual"
    assert set(last["pesticide"]) == {"id", "name", "item_name", "moa"}
    assert last["pesticide"]["id"] == PESTICIDE_ID


def test_groups_by_field_and_orders_by_id(db, make_user, make_field, make_zone):
    uid = make_user("farmer")
    first, second = make_field(uid), make_field(uid)
    a, b = make_zone(first, uid), make_zone(second, uid)
    c = make_zone(first, uid)
    result = zone_service.summaries(db, [first, second])
    assert [z["id"] for z in result[first]] == [a, c]
    assert [z["id"] for z in result[second]] == [b]
    assert zone_service.summaries(db, []) == {}


def test_field_without_zones_is_missing(db, make_user, make_field):
    field_id = make_field(make_user("farmer"))
    assert zone_service.summaries(db, [field_id]) == {}
