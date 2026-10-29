Ring = list[tuple[float, float]]
Polygon = list[Ring]  # 첫 링 = 바깥 경계, 나머지 = 구멍
MultiPolygon = list[Polygon]


def _ring_area(ring: Ring) -> float:
    # 신발끈 공식. 링 방향과 무관하게 양수
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:]))) / 2


def multipolygon_area(polygons: MultiPolygon) -> float:
    return sum(
        _ring_area(outer) - sum(_ring_area(hole) for hole in holes)
        for outer, *holes in polygons
    )
