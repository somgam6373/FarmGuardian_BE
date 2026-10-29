import uuid
from datetime import date, timedelta

import pytest

from app.catalog.application import catalog_service as catalog
from app.spraying.application import spray_service as svc

TODAY = date(2026, 10, 29)
A, B = [e.pesticide.id for e in catalog.list_pesticides(1)[:2]]


@pytest.fixture
def zones(make_user, make_field, make_zone):
    uid = make_user("farmer")
    field = make_field(uid)
    return make_zone(field, uid), make_zone(field, uid)


def record(db, zone, pesticide_id=A, sprayed_on=TODAY):
    return svc.record_spray(
        db,
        zone,
        pesticide_id=pesticide_id,
        sprayed_on=sprayed_on,
        source="manual",
        request_id=uuid.uuid4(),
        allow_duplicate=True,
        today=TODAY,
    )[0]


def test_history_is_newest_first_with_the_pesticide_resolved(db, zones):
    old = record(db, zones[0], A, TODAY - timedelta(days=9))
    first = record(db, zones[0], A, TODAY)
    second = record(db, zones[0], B, TODAY)
    views = svc.history(db, zones[0])

    assert [v.spray.id for v in views] == [second.spray.id, first.spray.id, old.spray.id]
    assert [v.pesticide for v in views] == [catalog.get_pesticide(p) for p in (B, A, A)]


def test_history_is_not_paged(db, zones):
    for day in range(25):
        record(db, zones[0], A, TODAY - timedelta(days=day))

    assert len(svc.history(db, zones[0])) == 25 > 20


def test_history_excludes_other_zones_and_is_empty_for_a_new_zone(db, zones):
    record(db, zones[1])

    assert svc.history(db, zones[0]) == []
    assert len(svc.history(db, zones[1])) == 1
