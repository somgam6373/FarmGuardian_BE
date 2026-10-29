import pytest

from app.farm.domain.geometry import multipolygon_area
from app.farm.domain.split import area_left_of, cut_positions


def rect(x0, y0, x1, y1):
    return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]]


# 아래 띠 0~100 × 0~10 위에 0~20 × 10~50 기둥을 얹은 L자 (면적 1800)
L_SHAPE = [[[(0, 0), (100, 0), (100, 10), (20, 10), (20, 50), (0, 50), (0, 0)]]]
PARALLELOGRAM = [[[(0, 0), (100, 0), (120, 20), (20, 20), (0, 0)]]]
WITH_HOLE = [rect(0, 0, 100, 20)[0:1] + rect(10, 5, 30, 15)[0:1]]


def assert_cuts(polygons, ratios, cuts):
    total = multipolygon_area(polygons)
    for k, x in enumerate(cuts, start=1):
        target = total * sum(ratios[:k]) / sum(ratios)
        assert abs(area_left_of(polygons, x) - target) <= 0.001 * total


@pytest.mark.parametrize(
    "polygons, ratios, expected",
    [
        ([rect(0, 0, 100, 20)], [1, 1], [50]),
        ([rect(0, 0, 100, 20)], [6, 4], [60]),
        ([rect(0, 0, 90, 10)], [1, 1, 1], [30, 60]),
        (L_SHAPE, [1, 1], [18]),
        (PARALLELOGRAM, [1, 1], [60]),
        (WITH_HOLE, [1, 1], [55]),
    ],
)
def test_known_cuts(polygons, ratios, expected):
    cuts = cut_positions(polygons, ratios)

    assert cuts == pytest.approx(expected, abs=0.2)
    assert_cuts(polygons, ratios, cuts)


def test_one_zone_has_no_cut():
    assert cut_positions([rect(0, 0, 100, 20)], [3]) == []


def test_two_pieces_cut_in_the_gap():
    polygons = [rect(0, 0, 10, 10), rect(20, 0, 30, 10)]

    [x] = cut_positions(polygons, [1, 1])

    assert 9.99 <= x <= 20.01


def test_deterministic():
    assert cut_positions(L_SHAPE, [3, 2, 5]) == cut_positions(L_SHAPE, [3, 2, 5])


def test_area_left_of():
    field = [rect(0, 0, 100, 20)]

    assert area_left_of(field, -5) == 0
    assert area_left_of(field, 25) == pytest.approx(500)
    assert area_left_of(field, 200) == pytest.approx(2000)
    assert area_left_of(WITH_HOLE, 20) == pytest.approx(300)


def test_far_from_origin():
    # 실제 EPSG:5179 좌표 크기에서도 오차 안에 든다
    field = [rect(990000, 1970000, 990100, 1970020)]

    cuts = cut_positions(field, [6, 4])

    assert cuts == pytest.approx([990060], abs=0.2)
    assert_cuts(field, [6, 4], cuts)


def test_clockwise_ring():
    ccw = [rect(0, 0, 100, 20)]
    cw = [[ccw[0][0][::-1]]]

    assert cut_positions(cw, [6, 4]) == pytest.approx(cut_positions(ccw, [6, 4]))


@pytest.mark.parametrize("ratios", [[1, 9], [1, 1, 8], [1] * 10])
def test_uneven_and_many_ratios(ratios):
    cuts = cut_positions(L_SHAPE, ratios)

    assert len(cuts) == len(ratios) - 1
    assert all(a < b for a, b in zip(cuts, cuts[1:]))
    assert_cuts(L_SHAPE, ratios, cuts)


@pytest.mark.parametrize(
    "polygons, ratios",
    [
        ([rect(0, 0, 10, 10)], []),
        ([rect(0, 0, 10, 10)], [1, 0]),
        ([rect(0, 0, 0, 10)], [1, 1]),
    ],
)
def test_invalid_input_raises(polygons, ratios):
    with pytest.raises(ValueError):
        cut_positions(polygons, ratios)
