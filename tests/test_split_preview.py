from math import cos, radians, sin

import pytest
from sqlalchemy import text

from app.farm.application import field_service
from app.farm.infrastructure import field_repository, split_repository
from app.farm.infrastructure.integrations.farmmap import FarmmapParcel


def rect(x0, y0, x1, y1):
    return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]]


def make(db, uid, *polygons):
    parcels = [
        FarmmapParcel(str(i), "1" * 19, "1전", "밭", 2022, [polygon])
        for i, polygon in enumerate(polygons, start=1)
    ]
    return field_repository.insert_field(db, uid, "f", parcels)


def areas(pieces):
    return [p["area_m2"] for p in pieces]


def bbox(piece):
    points = [pt for polygon in piece["geometry"]["coordinates"] for pt in polygon[0]]
    xs, ys = [x for x, _ in points], [y for _, y in points]
    return min(xs), min(ys), max(xs), max(ys)


@pytest.fixture
def uid(make_user):
    return make_user("farmer")


def test_crosswise_rectangle(db, uid):
    pieces = field_service.split_preview(db, make(db, uid, rect(0, 0, 20, 10)), "crosswise", [1, 1])
    assert areas(pieces) == [100.0, 100.0]
    assert bbox(pieces[0])[2] == pytest.approx(10)  # 서쪽부터
    assert set(pieces[0]) == {"geometry", "area_m2"}
    assert "crs" not in pieces[0]["geometry"]


def test_lengthwise_rectangle(db, uid):
    field_id = make(db, uid, rect(0, 0, 20, 10))
    pieces = field_service.split_preview(db, field_id, "lengthwise", [1, 1])
    assert areas(pieces) == [100.0, 100.0]
    assert bbox(pieces[0])[3] == pytest.approx(5)  # 남쪽부터


def test_ratio_areas(db, uid):
    pieces = field_service.split_preview(db, make(db, uid, rect(0, 0, 20, 10)), "crosswise", [6, 4])
    assert areas(pieces) == pytest.approx([120, 80], abs=0.2)


def test_rotated_rectangle(db, uid):
    a = radians(30)
    ring = [(x * cos(a) - y * sin(a), x * sin(a) + y * cos(a))
            for x, y in [(0, 0), (30, 0), (30, 10), (0, 10), (0, 0)]]
    pieces = field_service.split_preview(db, make(db, uid, [ring]), "crosswise", [1, 1, 1])
    assert areas(pieces) == pytest.approx([100, 100, 100], abs=0.2)


def test_vertical_field_order(db, uid):
    pieces = field_service.split_preview(db, make(db, uid, rect(0, 0, 10, 20)), "crosswise", [1, 1])
    assert areas(pieces) == [100.0, 100.0]
    assert bbox(pieces[0])[3] == pytest.approx(10)  # 남쪽부터


def test_l_shape_ratios(db, uid):
    l_shape = [[(0, 0), (100, 0), (100, 10), (20, 10), (20, 50), (0, 50), (0, 0)]]
    pieces = field_service.split_preview(db, make(db, uid, l_shape), "crosswise", [1, 1])
    assert areas(pieces) == pytest.approx([900, 900], abs=1.8)


def test_two_part_field(db, uid):
    field_id = make(db, uid, rect(0, 0, 10, 10), rect(100, 0, 110, 10))
    pieces = field_service.split_preview(db, field_id, "crosswise", [1, 1])
    assert areas(pieces) == [100.0, 100.0]


def test_pieces_cover_field(db, uid):
    l_shape = [[(0, 0), (100, 0), (100, 10), (20, 10), (20, 50), (0, 50), (0, 0)]]
    field_id = make(db, uid, l_shape)
    strips = field_service.split_strips_for(db, field_id, "lengthwise", [1, 2, 3])
    piece = split_repository.piece_sql("s")
    overlap = db.scalar(
        text(
            f"WITH p AS (SELECT n, {piece} AS g "
            "FROM field f, unnest(CAST(:strips AS text[])) WITH ORDINALITY AS u(s, n) "
            "WHERE f.id = :id) "
            "SELECT coalesce(sum(ST_Area(ST_Intersection(a.g, b.g))), 0) "
            "FROM p a JOIN p b ON a.n < b.n"
        ),
        {"id": field_id, "strips": strips},
    )
    assert overlap < 0.01
    total = field_repository.get_field(db, field_id).area_m2
    pieces = field_service.split_preview(db, field_id, "lengthwise", [1, 2, 3])
    assert sum(areas(pieces)) == pytest.approx(total, rel=0.001)


def test_square_field_is_deterministic(db, uid):
    field_id = make(db, uid, rect(0, 0, 10, 10))
    first = field_service.split_preview(db, field_id, "crosswise", [1, 2])
    assert field_service.split_preview(db, field_id, "crosswise", [1, 2]) == first


def test_preview_twice_identical(db, uid):
    l_shape = [[(0, 0), (100, 0), (100, 10), (20, 10), (20, 50), (0, 50), (0, 0)]]
    field_id = make(db, uid, l_shape)
    first = field_service.split_preview(db, field_id, "lengthwise", [3, 1, 2])
    assert field_service.split_preview(db, field_id, "lengthwise", [3, 1, 2]) == first


def test_single_ratio_is_whole_field(db, uid):
    field_id = make(db, uid, rect(0, 0, 20, 10))
    [piece] = field_service.split_preview(db, field_id, "crosswise", [3])
    assert piece["area_m2"] == 200.0
