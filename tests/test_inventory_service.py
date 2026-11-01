import pytest

from app.catalog.application import catalog_service
from app.core.errors import AppError
from app.inventory.application import service

IDS = sorted(drug.id for drug in catalog_service.all_pesticides())
SMALL, LARGE = IDS[0], IDS[-1]


def test_add_is_idempotent_and_lists_in_added_order(db, make_user):
    uid = make_user("farmer")

    assert [service.add_drug(db, uid, LARGE), service.add_drug(db, uid, SMALL)] == [True, True]
    assert service.add_drug(db, uid, LARGE) is False
    assert service.list_drugs(db, uid) == [LARGE, SMALL]  # 담은 순서이지 id 순서가 아니다


def test_remove_deletes_one_row_and_404s_when_absent(db, make_user):
    uid = make_user("farmer")
    service.add_drug(db, uid, SMALL)
    service.add_drug(db, uid, LARGE)

    service.remove_drug(db, uid, SMALL)

    assert service.list_drugs(db, uid) == [LARGE]
    with pytest.raises(AppError) as exc:
        service.remove_drug(db, uid, SMALL)
    assert (exc.value.code, exc.value.status) == ("NOT_FOUND", 404)


def test_users_are_isolated(db, make_user):
    owner, other = make_user("owner"), make_user("other")
    service.add_drug(db, owner, SMALL)

    assert service.list_drugs(db, other) == []
    with pytest.raises(AppError) as exc:
        service.remove_drug(db, other, SMALL)
    assert exc.value.status == 404
    assert service.list_drugs(db, owner) == [SMALL]


@pytest.mark.parametrize("drug_id", [0, -1, 2**40])
def test_ids_outside_the_catalog_never_reach_the_database(drug_id):
    # db=None: 데이터베이스를 건드리면 AttributeError가 나서 이 테스트가 깨진다
    with pytest.raises(AppError) as add_error:
        service.add_drug(None, 1, drug_id)
    assert add_error.value.status == 422
    assert add_error.value.details["errors"][0]["loc"] == ["body", "drug_id"]

    with pytest.raises(AppError) as remove_error:
        service.remove_drug(None, 1, drug_id)
    assert remove_error.value.status == 404
