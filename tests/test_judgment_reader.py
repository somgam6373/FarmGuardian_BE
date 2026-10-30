from datetime import UTC, datetime, timedelta

import pytest
from fastapi.encoders import jsonable_encoder
from sqlalchemy import event, text

from app.catalog.application import catalog_service
from app.core.time import KST
from app.judgment.application import reader
from tests.judgment_scenarios import pests_with_drugs, pool

PEST = pests_with_drugs(1)[0]
DRUG = pool(1, PEST)[0]
GONE = 2_000_000_000  # 카탈로그에 없는 id
T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def minute(n):
    return T0 + timedelta(minutes=n)


@pytest.fixture
def zone(make_user, make_field, make_zone):
    uid = make_user("farmer")
    return make_zone(make_field(uid), uid)


@pytest.fixture
def other_zone(make_user, make_field, make_zone):
    uid = make_user("neighbor")
    return make_zone(make_field(uid), uid)


@pytest.fixture
def empty_zone(make_user, make_field, make_zone):
    uid = make_user("idle")
    return make_zone(make_field(uid), uid)


def add(db, zone_id, *, pest_id=None, pesticide_id=DRUG.id, verdict="OK", at=None):
    return db.scalar(
        text(
            "INSERT INTO judgment (zone_id, pest_id, pesticide_id, apply_date, verdict, result, "
            "created_at) VALUES (:z, :pest, :drug, '2026-10-29', :v, '{}'::jsonb, "
            "COALESCE(CAST(:at AS timestamptz), now())) RETURNING id"
        ),
        {"z": zone_id, "pest": pest_id, "drug": pesticide_id, "v": verdict, "at": at},
    )


def ids(briefs):
    return [brief["judgment_id"] for brief in briefs]


def test_brief_has_exactly_the_spec_shape(db, zone):
    judgment_id = add(db, zone, pest_id=PEST, verdict="CAUTION")

    [brief] = reader.recent_judgments(db, zone)

    assert set(brief) == {"judgment_id", "created_at", "pesticide", "pest", "verdict"}
    assert brief["judgment_id"] == judgment_id
    assert brief["pesticide"] == {"id": DRUG.id, "name": DRUG.name, "item_name": DRUG.item_name}
    assert brief["pest"] == {"id": PEST, "name": catalog_service.get_pest_card(PEST).name}
    assert brief["verdict"] == "CAUTION"


def test_pest_is_null_when_none_was_given(db, zone):
    add(db, zone)

    [brief] = reader.recent_judgments(db, zone)

    assert brief["pest"] is None


def test_created_at_is_kst_seconds_on_the_wire(db, zone):
    # DB 세션 시간대와 상관없이 KST로 나가야 한다 (배포 DB는 UTC일 수 있다)
    db.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    add(db, zone, at=datetime(2026, 10, 30, 7, 6, 5, 123456, tzinfo=UTC))

    [brief] = reader.recent_judgments(db, zone)

    assert brief["created_at"] == datetime(2026, 10, 30, 16, 6, 5, tzinfo=KST)
    assert jsonable_encoder(brief)["created_at"] == "2026-10-30T16:06:05+09:00"


def test_newest_first_and_higher_id_first_on_equal_times(db, zone):
    a = add(db, zone, at=minute(1))
    b = add(db, zone, at=minute(3))
    c = add(db, zone, at=minute(2))
    d = add(db, zone, at=minute(3))

    assert ids(reader.recent_judgments(db, zone)) == [d, b, c, a]


def test_default_limit_is_five_and_the_argument_applies(db, zone):
    newest_first = [add(db, zone, at=minute(i)) for i in range(7)][::-1]

    assert ids(reader.recent_judgments(db, zone)) == newest_first[:5]
    assert ids(reader.recent_judgments(db, zone, limit=2)) == newest_first[:2]


def test_other_zones_never_leak_and_an_empty_zone_is_empty(db, zone, other_zone):
    add(db, other_zone)

    assert reader.recent_judgments(db, zone) == []


def test_ids_that_left_the_catalog_are_skipped(db, zone):
    add(db, zone, pesticide_id=GONE, at=minute(3))
    add(db, zone, pest_id=GONE, at=minute(2))
    keep = add(db, zone, at=minute(1))

    assert ids(reader.recent_judgments(db, zone)) == [keep]


def test_each_zone_gets_its_newest_judgment_and_empty_zones_are_absent(
    db, zone, other_zone, empty_zone
):
    add(db, zone, at=minute(1))
    newest = add(db, zone, at=minute(5))
    add(db, zone, at=minute(3))
    add(db, other_zone, at=minute(9))
    other_newest = add(db, other_zone, at=minute(10))

    found = reader.last_judgments(db, [zone, other_zone, empty_zone])

    assert set(found) == {zone, other_zone}
    assert found[zone]["judgment_id"] == newest
    assert found[other_zone]["judgment_id"] == other_newest


def test_equal_times_pick_the_higher_id(db, zone):
    add(db, zone, at=minute(1))
    higher = add(db, zone, at=minute(1))

    assert reader.last_judgments(db, [zone])[zone]["judgment_id"] == higher


def test_zones_not_asked_for_are_not_returned_and_empty_input_gives_empty_dict(
    db, zone, other_zone
):
    add(db, zone)
    add(db, other_zone)

    assert set(reader.last_judgments(db, [zone])) == {zone}
    assert reader.last_judgments(db, []) == {}


def test_a_newest_row_with_a_stale_id_leaves_the_zone_out(db, zone):
    add(db, zone, at=minute(1))
    add(db, zone, pesticide_id=GONE, at=minute(2))

    assert reader.last_judgments(db, [zone]) == {}


def test_one_statement_for_many_zones(db, zone, other_zone, empty_zone):
    statements = []

    def count(conn, cursor, statement, *args):
        statements.append(statement)

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", count)
    try:
        reader.last_judgments(db, [zone, other_zone, empty_zone])
    finally:
        event.remove(bind, "before_cursor_execute", count)

    assert len(statements) == 1
