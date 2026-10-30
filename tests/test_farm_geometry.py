from app.farm.domain.geometry import multipolygon_area, to_wkt

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


def test_to_wkt():
    triangle = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)]
    assert to_wkt([[triangle]]) == "MULTIPOLYGON(((0.0 0.0,1.0 0.0,1.0 1.0,0.0 0.0)))"


def test_to_wkt_keeps_holes_and_pieces():
    assert to_wkt([[SQUARE, HOLE], [SQUARE]]).count("),(") == 2
