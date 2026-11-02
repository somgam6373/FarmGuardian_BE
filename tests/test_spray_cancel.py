import pytest

from app.core.errors import AppError
from app.spraying.application import spray_service as svc
from tests.judgment_scenarios import pests_with_drugs
from tests.test_spray_service import record, total


@pytest.fixture
def zones(make_user, make_field, make_zone):
    uid = make_user("farmer")
    field = make_field(uid)
    return make_zone(field, uid), make_zone(field, uid)


def test_an_unknown_pest_is_422_before_anything_is_stored():
    with pytest.raises(AppError) as info:
        record(None, 1, pest_id=999999)  # 검증이 먼저라 DB를 건드리지 않는다

    assert (info.value.status, info.value.code) == (422, "VALIDATION_ERROR")
    assert info.value.details["errors"][0]["loc"] == ["body", "pest_id"]
    assert "999999" not in str(info.value.details)


def test_cancelled_spray_leaves_history_duplicates_and_the_default_listing(db, zones):
    view, _ = record(db, zones[0])
    svc.cancel_spray(db, zones[0], view.spray.id)

    assert svc.history(db, zones[0]) == [] and total(db, zones[0]) == 0
    record(db, zones[0])  # 같은 구역·약제·날짜인데 DuplicateSpray가 아니다


def test_include_cancelled_marks_the_row(db, zones):
    view, _ = record(db, zones[0])
    svc.cancel_spray(db, zones[0], view.spray.id)
    count, rows = svc.list_sprays(db, zones[0], include_cancelled=True)

    assert (count, [r.spray.cancelled for r in rows]) == (1, [True])


def test_cancel_twice_is_fine_and_restore_brings_the_row_back(db, zones):
    view, _ = record(db, zones[0])
    sid = view.spray.id
    svc.cancel_spray(db, zones[0], sid)
    svc.cancel_spray(db, zones[0], sid)

    assert svc.restore_spray(db, zones[0], sid).spray.cancelled is False
    assert total(db, zones[0]) == 1


def test_cancel_and_restore_are_scoped_to_the_zone(db, zones):
    view, _ = record(db, zones[0])
    for call in (svc.cancel_spray, svc.restore_spray):
        with pytest.raises(AppError) as info:
            call(db, zones[1], view.spray.id)

        assert (info.value.status, info.value.code) == (404, "NOT_FOUND")


def test_pest_id_is_stored_and_echoed_as_a_pest(db, zones):
    pest = pests_with_drugs(1)[0]
    view, _ = record(db, zones[0], pest_id=pest)

    assert view.spray.pest_id == pest and view.pest.id == pest
    assert record(db, zones[0], pest_id=None, allow_duplicate=True)[0].pest is None
