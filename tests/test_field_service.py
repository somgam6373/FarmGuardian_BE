import threading
import time

import pytest
from sqlalchemy import text

from app.core.errors import AppError
from app.farm.application import field_service
from app.farm.infrastructure import field_repository
from app.farm.infrastructure.integrations import farmmap
from tests.farm_support import square

FIELD_KEYS = {"id", "name", "area_m2", "geometry", "bbox", "zones"}


@pytest.fixture
def fake_farmmap(monkeypatch):
    """id → 정사각형 필지. missing에 있는 id는 None, failing에 있는 id는 502."""
    calls, missing, failing = [], set(), set()

    def fake(farmmap_id, *, client=None):
        calls.append(farmmap_id)
        if farmmap_id in failing:
            raise AppError("UPSTREAM_ERROR", 502, "팜맵 조회에 실패했습니다", {"source": "farmmap"})
        if farmmap_id in missing:
            return None
        return square(farmmap_id, x0=10 * (int(farmmap_id) - 1))

    monkeypatch.setattr(farmmap, "parcel_by_id", fake)
    return calls, missing, failing


def count(db, table):
    return db.scalar(text(f"SELECT count(*) FROM {table}"))


def test_create_returns_field(db, make_user, fake_farmmap):
    field = field_service.create_field(db, make_user("farmer"), "앞밭", ["1", "2"])
    assert set(field) == FIELD_KEYS
    assert field["name"] == "앞밭"
    assert field["area_m2"] == 200.0
    assert field["bbox"] == [0, 0, 20, 10]
    assert field["zones"] == []


def test_already_used_is_409_before_farmmap(db, make_user, fake_farmmap):
    uid = make_user("farmer")
    field_service.create_field(db, uid, "f", ["1"])
    calls = fake_farmmap[0]
    calls.clear()
    with pytest.raises(AppError) as error:
        field_service.create_field(db, uid, "g", ["2", "1"])
    assert error.value.code == "PARCEL_ALREADY_USED" and error.value.status == 409
    assert error.value.details == {"farmmap_ids": ["1"]}
    assert calls == []


def test_unknown_ids_are_422_with_indexes(db, make_user, fake_farmmap):
    fake_farmmap[1].update({"2", "4"})
    with pytest.raises(AppError) as error:
        field_service.create_field(db, make_user("farmer"), "f", ["1", "2", "3", "4"])
    assert error.value.code == "VALIDATION_ERROR" and error.value.status == 422
    errors = error.value.details["errors"]
    assert [e["loc"] for e in errors] == [
        ["body", "parcel_farmmap_ids", 1],
        ["body", "parcel_farmmap_ids", 3],
    ]
    assert {e["type"] for e in errors} == {"not_found"}


def test_upstream_error_saves_nothing(db, make_user, fake_farmmap):
    uid = make_user("farmer")
    fake_farmmap[2].add("3")
    with pytest.raises(AppError) as error:
        field_service.create_field(db, uid, "f", ["1", "2", "3"])
    assert error.value.status == 502
    assert count(db, "field") == 0 and count(db, "field_parcel") == 0


def test_race_on_insert_is_409(db, make_user, fake_farmmap, monkeypatch):
    uid = make_user("farmer")
    field_service.create_field(db, uid, "f", ["1"])
    real = field_repository.used_farmmap_ids
    calls = []

    def first_call_misses(*args):
        calls.append(args)
        return {} if len(calls) == 1 else real(*args)

    monkeypatch.setattr(field_repository, "used_farmmap_ids", first_call_misses)
    with pytest.raises(AppError) as error:
        field_service.create_field(db, uid, "g", ["1"])
    assert error.value.status == 409 and error.value.details == {"farmmap_ids": ["1"]}
    assert db.scalar(text("SELECT 1")) == 1
    assert count(db, "field") == 1


def test_at_most_8_concurrent_fetches(db, make_user, monkeypatch):
    lock, state = threading.Lock(), {"now": 0, "peak": 0}

    def slow(farmmap_id, *, client=None):
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        time.sleep(0.02)
        with lock:
            state["now"] -= 1
        return square(farmmap_id, x0=10 * int(farmmap_id))

    monkeypatch.setattr(farmmap, "parcel_by_id", slow)
    ids = [str(i) for i in range(1, 21)]
    field = field_service.create_field(db, make_user("farmer"), "f", ids)
    assert 1 < state["peak"] <= 8
    assert field["area_m2"] == 2000.0


def test_list_fields_includes_zones(db, make_user, make_zone, fake_farmmap):
    me, other = make_user("me"), make_user("other")
    first = field_service.create_field(db, me, "a", ["1"])
    field_service.create_field(db, other, "x", ["1"])
    second = field_service.create_field(db, me, "b", ["2"])
    zone_id = make_zone(second["id"], me)
    fields = field_service.list_fields(db, me)
    assert [f["id"] for f in fields] == [first["id"], second["id"]]
    assert fields[0]["zones"] == []
    assert [z["id"] for z in fields[1]["zones"]] == [zone_id]


def test_delete_field(db, make_user, fake_farmmap):
    uid = make_user("farmer")
    field = field_service.create_field(db, uid, "f", ["1"])
    field_service.delete_field(db, field["id"])
    assert field_service.list_fields(db, uid) == []
