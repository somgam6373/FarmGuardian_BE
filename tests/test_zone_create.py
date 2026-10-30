from datetime import date

import pytest
from sqlalchemy import text

from app.core.errors import AppError
from app.farm.application import field_service
from app.farm.infrastructure import field_repository
from app.farm.infrastructure.integrations.farmmap import FarmmapParcel

ZONE_KEYS = {
    "id", "field_id", "name", "crop", "planted_at", "history_confirmed", "area_m2", "geometry",
    "bbox",
}
RECT = [[(0, 0), (20, 0), (20, 10), (0, 10), (0, 0)]]
SPECS = [
    {"name": "앞", "crop_id": 1, "planted_at": None},
    {"name": "뒤", "crop_id": 2, "planted_at": date(2026, 3, 1)},
]


@pytest.fixture
def farm(db, make_user):
    uid = make_user("farmer")
    parcel = FarmmapParcel("1", "1" * 19, "1전", "밭", 2022, [RECT])
    return uid, field_repository.insert_field(db, uid, "f", [parcel])


def zone_count(db):
    return db.scalar(text("SELECT count(*) FROM zone"))


def test_create_returns_zones_in_order(db, farm):
    uid, field_id = farm
    first, second = field_service.create_zones(db, field_id, uid, "crosswise", [1, 1], SPECS)
    assert set(first) == ZONE_KEYS
    assert first["field_id"] == field_id and first["name"] == "앞"
    assert first["crop"] == {"id": 1, "name": "감자"}
    assert second["crop"] == {"id": 2, "name": "배추"}
    assert second["planted_at"] == date(2026, 3, 1)
    assert first["history_confirmed"] is False
    assert [first["area_m2"], second["area_m2"]] == [100.0, 100.0]
    assert first["bbox"] == [0.0, 0.0, 10.0, 10.0]  # 서쪽부터
    assert first["id"] < second["id"]


def test_create_matches_preview(db, farm):
    uid, field_id = farm
    preview = field_service.split_preview(db, field_id, "lengthwise", [6, 4])
    zones = field_service.create_zones(db, field_id, uid, "lengthwise", [6, 4], SPECS)
    assert [z["geometry"] for z in zones] == [p["geometry"] for p in preview]
    assert [z["area_m2"] for z in zones] == [p["area_m2"] for p in preview]


def test_already_split_is_409(db, farm):
    uid, field_id = farm
    field_service.create_zones(db, field_id, uid, "crosswise", [1, 1], SPECS)
    with pytest.raises(AppError) as error:
        field_service.create_zones(db, field_id, uid, "crosswise", [1, 1], SPECS)
    assert error.value.code == "FIELD_ALREADY_SPLIT" and error.value.status == 409
    assert zone_count(db) == 2


def test_unknown_crop_is_422(db, farm):
    uid, field_id = farm
    specs = [SPECS[0], {**SPECS[1], "crop_id": 999}]
    with pytest.raises(AppError) as error:
        field_service.create_zones(db, field_id, uid, "crosswise", [1, 1], specs)
    assert error.value.status == 422
    [err] = error.value.details["errors"]
    assert err["loc"] == ["body", "zones", 1, "crop_id"] and err["type"] == "not_found"
    assert zone_count(db) == 0


def test_field_list_shows_new_zones(db, farm):
    uid, field_id = farm
    zones = field_service.create_zones(db, field_id, uid, "crosswise", [1, 1], SPECS)
    [field] = field_service.list_fields(db, uid)
    assert [z["id"] for z in field["zones"]] == [z["id"] for z in zones]
