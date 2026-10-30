import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.farm.infrastructure import field_repository as repo
from app.farm.infrastructure.integrations.farmmap import FarmmapParcel
from tests.farm_support import square


def test_adjacent_parcels_union_area(db, make_user):
    uid = make_user("farmer")
    field = repo.get_field(db, repo.insert_field(db, uid, "앞밭", [square("1"), square("2", 10)]))
    assert field.name == "앞밭"
    assert field.area_m2 == 200.0
    assert field.geometry["type"] == "MultiPolygon"
    assert "crs" not in field.geometry
    assert len(field.geometry["coordinates"]) == 1
    assert field.bbox == [0, 0, 20, 10]


def test_far_apart_parcels_stay_one_field(db, make_user):
    uid = make_user("farmer")
    field = repo.get_field(db, repo.insert_field(db, uid, "f", [square("1"), square("2", 100)]))
    assert len(field.geometry["coordinates"]) == 2
    assert field.area_m2 == 200.0


def test_parcel_rows_saved(db, make_user):
    uid = make_user("farmer")
    field_id = repo.insert_field(db, uid, "f", [square("1"), square("2", 10)])
    rows = db.execute(
        text(
            "SELECT farmmap_id, pnu, lnm, land_use, vdpt_yr, user_id FROM field_parcel "
            "WHERE field_id = :f ORDER BY farmmap_id"
        ),
        {"f": field_id},
    ).all()
    assert [tuple(r) for r in rows] == [
        ("1", "1" * 19, "1전", "밭", 2022, uid),
        ("2", "1" * 19, "1전", "밭", 2022, uid),
    ]


def test_used_farmmap_ids_only_mine(db, make_user):
    me, other = make_user("me"), make_user("other")
    repo.insert_field(db, other, "f", [square("1")])
    assert repo.used_farmmap_ids(db, me, ["1", "2"]) == {}
    mine = repo.insert_field(db, me, "f", [square("2")])
    assert repo.used_farmmap_ids(db, me, ["1", "2"]) == {"2": mine}


def test_duplicate_parcel_raises_integrity_error(db, make_user):
    uid = make_user("farmer")
    repo.insert_field(db, uid, "f", [square("1")])
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            repo.insert_field(db, uid, "g", [square("1")])


def test_list_fields_order_and_owner(db, make_user):
    me, other = make_user("me"), make_user("other")
    first = repo.insert_field(db, me, "a", [square("1")])
    repo.insert_field(db, other, "x", [square("2")])
    second = repo.insert_field(db, me, "b", [square("3")])
    assert [f.id for f in repo.list_fields(db, me)] == [first, second]


def test_delete_field_cascades_zone(db, make_user, make_zone):
    uid = make_user("farmer")
    field_id = repo.insert_field(db, uid, "f", [square("1")])
    zone_id = make_zone(field_id, uid)
    repo.delete_field(db, field_id)
    assert db.scalar(text("SELECT count(*) FROM zone WHERE id = :z"), {"z": zone_id}) == 0
    assert repo.used_farmmap_ids(db, uid, ["1"]) == {}


def test_bbox_rounded_to_one_decimal(db, make_user):
    uid = make_user("farmer")
    field = repo.get_field(db, repo.insert_field(db, uid, "f", [square("1", x0=0.04)]))
    assert field.bbox == [0.0, 0.0, 10.0, 10.0]


def bowtie(farmmap_id: str) -> FarmmapParcel:
    # 자기 교차 폴리곤. 팜맵 판독 도형에 섞일 수 있다
    ring = [(0.0, 0.0), (10.0, 10.0), (10.0, 0.0), (0.0, 10.0), (0.0, 0.0)]
    return FarmmapParcel(farmmap_id, "1" * 19, "1전", "밭", 2022, [[ring]])


def test_invalid_parcel_geometry_is_repaired(db, make_user):
    uid = make_user("farmer")
    field_id = repo.insert_field(db, uid, "f", [bowtie("1"), square("2", 20)])
    assert repo.get_field(db, field_id).area_m2 == 150.0
    assert db.scalar(
        text("SELECT bool_and(ST_IsValid(geom)) FROM field_parcel WHERE field_id = :f"),
        {"f": field_id},
    )
