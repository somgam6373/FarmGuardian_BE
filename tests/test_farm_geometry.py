from app.farm.domain.geometry import multipolygon_area

SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
HOLE = [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0), (4.0, 4.0)]


def test_square_area():
    assert multipolygon_area([[SQUARE]]) == 100


def test_reversed_ring_is_positive():
    assert multipolygon_area([[SQUARE[::-1]]]) == 100


def test_hole_is_subtracted():
    assert multipolygon_area([[SQUARE, HOLE]]) == 96


def test_pieces_are_summed():
    assert multipolygon_area([[SQUARE], [SQUARE]]) == 200
