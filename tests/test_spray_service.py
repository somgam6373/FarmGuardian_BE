import uuid
from datetime import date, timedelta

import pytest

from app.catalog.application import catalog_service as catalog
from app.core.errors import AppError
from app.spraying.application import spray_service as svc
from app.spraying.application.spray_service import DuplicateSpray
from app.spraying.infrastructure import repository

TODAY = date(2026, 10, 29)
A, B = [e.pesticide.id for e in catalog.list_pesticides(1)[:2]]


@pytest.fixture
def zones(make_user, make_field, make_zone):
    uid = make_user("farmer")
    field = make_field(uid)
    return make_zone(field, uid), make_zone(field, uid)


def record(db, zone, pesticide_id=A, **kw):
    args = {
        "pesticide_id": pesticide_id,
        "sprayed_on": TODAY,
        "source": "manual",
        "request_id": uuid.uuid4(),
        "allow_duplicate": False,
        "today": TODAY,
    }
    return svc.record_spray(db, zone, **{**args, **kw})


def total(db, zone):
    return svc.list_sprays(db, zone)[0]


def test_record_returns_the_saved_spray_and_created_flag(db, zones):
    view, created = record(db, zones[0], source="app")

    assert created is True
    assert (view.spray.pesticide_id, view.spray.sprayed_on, view.spray.source) == (A, TODAY, "app")
    assert view.pesticide.id == A
    assert view.spray.id > 0


def test_omitted_date_defaults_to_today(db, zones):
    view, _ = record(db, zones[0], sprayed_on=None)

    assert view.spray.sprayed_on == TODAY


def test_today_and_past_are_valid_but_tomorrow_is_422(db, zones):
    record(db, zones[0], sprayed_on=TODAY)
    record(db, zones[0], sprayed_on=date(2020, 1, 1))
    with pytest.raises(AppError) as info:
        record(db, zones[0], sprayed_on=TODAY + timedelta(days=1))

    assert (info.value.status, info.value.code) == (422, "VALIDATION_ERROR")
    assert info.value.details["errors"][0]["loc"] == ["body", "sprayed_on"]
    assert "2026-10-30" not in str(info.value.details)
    assert total(db, zones[0]) == 2


def test_unknown_pesticide_is_422_and_stores_nothing(db, zones):
    with pytest.raises(AppError) as info:
        record(db, zones[0], 999999)

    assert (info.value.status, info.value.code) == (422, "VALIDATION_ERROR")
    assert info.value.details["errors"][0]["loc"] == ["body", "pesticide_id"]
    assert "999999" not in str(info.value.details)
    assert total(db, zones[0]) == 0


def test_same_request_id_returns_the_stored_spray_without_saving_again(db, zones):
    rid = uuid.uuid4()
    first, created_first = record(db, zones[0], request_id=rid)
    again, created_again = record(db, zones[0], request_id=rid)

    assert (created_first, created_again) == (True, False)
    assert again.spray.id == first.spray.id
    assert total(db, zones[0]) == 1


def test_replay_returns_the_original_even_if_the_retry_differs(db, zones):
    rid = uuid.uuid4()
    first, _ = record(db, zones[0], A, request_id=rid)
    again, created = record(
        db, zones[0], B, request_id=rid, sprayed_on=TODAY - timedelta(days=3)
    )

    assert created is False and again.spray.id == first.spray.id
    assert (again.spray.pesticide_id, again.spray.sprayed_on) == (A, TODAY)


def test_request_id_of_another_zone_is_422_and_leaks_nothing(db, zones):
    rid = uuid.uuid4()
    record(db, zones[0], request_id=rid)
    with pytest.raises(AppError) as info:
        record(db, zones[1], B, request_id=rid)

    assert (info.value.status, info.value.code) == (422, "VALIDATION_ERROR")
    assert info.value.details["errors"][0]["loc"] == ["body", "request_id"]
    assert total(db, zones[1]) == 0


def test_duplicate_raises_with_the_existing_spray_and_stores_nothing(db, zones):
    first, _ = record(db, zones[0])
    with pytest.raises(DuplicateSpray) as info:
        record(db, zones[0])

    assert info.value.existing.spray.id == first.spray.id
    assert info.value.existing.pesticide.id == A
    assert total(db, zones[0]) == 1


def test_allow_duplicate_saves_a_second_record(db, zones):
    first, _ = record(db, zones[0])
    second, created = record(db, zones[0], allow_duplicate=True)

    assert created is True and second.spray.id != first.spray.id
    assert total(db, zones[0]) == 2


def test_resending_a_409_request_id_with_allow_duplicate_saves(db, zones):
    record(db, zones[0])
    rid = uuid.uuid4()
    with pytest.raises(DuplicateSpray):
        record(db, zones[0], request_id=rid)
    _, created = record(db, zones[0], request_id=rid, allow_duplicate=True)

    assert created is True
    assert total(db, zones[0]) == 2


def test_existing_is_the_oldest_duplicate(db, zones):
    first, _ = record(db, zones[0])
    record(db, zones[0], allow_duplicate=True)
    with pytest.raises(DuplicateSpray) as info:
        record(db, zones[0])

    assert info.value.existing.spray.id == first.spray.id


@pytest.mark.parametrize(
    "change", [{"sprayed_on": TODAY - timedelta(days=1)}, {"pesticide_id": B}], ids=["date", "drug"]
)
def test_other_date_or_pesticide_is_not_a_duplicate(db, zones, change):
    record(db, zones[0])
    _, created = record(db, zones[0], **change)

    assert created is True


def test_same_spray_in_another_zone_is_not_a_duplicate(db, zones):
    record(db, zones[0])
    _, created = record(db, zones[1])

    assert created is True


def stale_first_lookup(monkeypatch):
    # 경쟁 요청이 막 저장한 뒤인데도 첫 조회는 빈손으로 돌아오는 상황
    real, calls = repository.find_by_request_id, []

    def stale(db, request_id):
        calls.append(request_id)
        return None if len(calls) == 1 else real(db, request_id)

    monkeypatch.setattr(repository, "find_by_request_id", stale)


@pytest.mark.parametrize("allow_duplicate", [False, True])
def test_lost_race_is_answered_as_a_replay(db, zones, monkeypatch, allow_duplicate):
    rid = uuid.uuid4()
    first, _ = record(db, zones[0], request_id=rid)
    stale_first_lookup(monkeypatch)
    again, created = record(db, zones[0], request_id=rid, allow_duplicate=allow_duplicate)

    assert created is False and again.spray.id == first.spray.id
    assert total(db, zones[0]) == 1


def test_insert_with_a_used_request_id_returns_none(db, zones):
    rid = uuid.uuid4()

    assert repository.insert(db, zones[0], A, TODAY, "manual", rid) is not None
    assert repository.insert(db, zones[0], B, TODAY, "app", rid) is None
    assert repository.page(db, zones[0], 20, 0)[0] == 1


def test_list_orders_by_date_then_id_descending(db, zones):
    old, _ = record(db, zones[0], A, sprayed_on=TODAY - timedelta(days=5))
    new_a, _ = record(db, zones[0], A, sprayed_on=TODAY)
    new_b, _ = record(db, zones[0], B, sprayed_on=TODAY)
    count, items = svc.list_sprays(db, zones[0])

    assert count == 3
    assert [v.spray.id for v in items] == [new_b.spray.id, new_a.spray.id, old.spray.id]


def test_list_pages_and_total_counts_everything(db, zones):
    ids = [
        record(db, zones[0], A, sprayed_on=TODAY - timedelta(days=i))[0].spray.id
        for i in range(5)
    ]
    count, page = svc.list_sprays(db, zones[0], limit=2, offset=1)

    assert count == 5
    assert [v.spray.id for v in page] == ids[1:3]
    assert svc.list_sprays(db, zones[0], limit=2, offset=10) == (5, [])


def test_list_excludes_other_zones_and_resolves_the_pesticide(db, zones):
    record(db, zones[0], A)
    record(db, zones[1], B)
    count, items = svc.list_sprays(db, zones[0])

    assert count == 1
    assert items[0].pesticide == catalog.get_pesticide(A)


def test_cancel_removes_the_record(db, zones):
    view, _ = record(db, zones[0])
    svc.cancel_spray(db, zones[0], view.spray.id)

    assert total(db, zones[0]) == 0


def test_cancel_twice_or_unknown_is_404(db, zones):
    view, _ = record(db, zones[0])
    svc.cancel_spray(db, zones[0], view.spray.id)
    for spray_id in (view.spray.id, 999999):
        with pytest.raises(AppError) as info:
            svc.cancel_spray(db, zones[0], spray_id)

        assert (info.value.status, info.value.code) == (404, "NOT_FOUND")


def test_cancel_of_another_zones_record_is_404_and_keeps_it(db, zones):
    view, _ = record(db, zones[1])
    with pytest.raises(AppError) as info:
        svc.cancel_spray(db, zones[0], view.spray.id)

    assert info.value.status == 404
    assert total(db, zones[1]) == 1
