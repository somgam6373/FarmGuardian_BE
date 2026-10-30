from math import cos, pi, radians, sin

import pytest

from app.farm.domain.geometry import multipolygon_area
from app.farm.domain.split import (
    area_left_of,
    cut_positions,
    long_side_angle,
    rotate,
    split_strips,
)


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


@pytest.mark.parametrize(
    "polygons, ratios, expected",
    [(L_SHAPE, [5, 4], [20]), (WITH_HOLE, [1, 1], [55]), (L_SHAPE, [1, 1], [18])],
)
def test_cut_is_precise_not_just_within_tolerance(polygons, ratios, expected):
    # 허용 오차(0.1%)에 들자마자 멈추면 균등 분할 구역끼리 면적이 눈에 띄게 달라진다
    assert cut_positions(polygons, ratios) == pytest.approx(expected, abs=1e-6)


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


def turned(points, angle):
    return [(x * cos(angle) - y * sin(angle), x * sin(angle) + y * cos(angle)) for x, y in points]


def bounds(ring):
    xs, ys = [x for x, _ in ring], [y for _, y in ring]
    return min(xs), min(ys), max(xs), max(ys)


def test_long_side_angle():
    assert long_side_angle(rect(0, 0, 20, 10)[0]) == pytest.approx(0.0)
    assert long_side_angle(rect(0, 0, 20, 10)[0][::-1]) == pytest.approx(0.0)
    assert long_side_angle([(20, 10), (0, 10), (0, 0), (20, 0), (20, 10)]) == pytest.approx(0.0)
    assert long_side_angle(rect(0, 0, 10, 20)[0]) == pytest.approx(pi / 2)
    tilted = turned([(0, 0), (30, 0), (30, 10), (0, 10), (0, 0)], radians(30))
    assert long_side_angle(tilted) == pytest.approx(radians(30))


def test_rotate_quarter_turn():
    [[ring]] = rotate([[[(1, 0), (2, 0), (2, 1), (1, 0)]]], pi / 2, (0, 0))
    expected = [(0, 1), (0, 2), (-1, 2), (0, 1)]
    for (x, y), (ex, ey) in zip(ring, expected):
        assert x == pytest.approx(ex, abs=1e-9) and y == pytest.approx(ey, abs=1e-9)


def test_strips_crosswise_rectangle():
    field = [rect(0, 0, 20, 10)]
    first, second = split_strips(field, field[0][0], "crosswise", [1, 1])
    assert bounds(first)[2] == pytest.approx(10)
    assert bounds(first)[0] < bounds(second)[0]  # 서쪽부터


def test_strips_lengthwise_rectangle():
    field = [rect(0, 0, 20, 10)]
    first, second = split_strips(field, field[0][0], "lengthwise", [1, 1])
    assert bounds(first)[3] == pytest.approx(5)
    assert bounds(first)[1] < bounds(second)[1]  # 남쪽부터


def test_single_ratio_one_strip():
    field = [rect(0, 0, 20, 10)]
    [strip] = split_strips(field, field[0][0], "crosswise", [3])
    minx, miny, maxx, maxy = bounds(strip)
    assert minx < 0 and miny < 0 and maxx > 20 and maxy > 10
