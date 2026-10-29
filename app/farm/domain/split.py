from app.farm.domain.geometry import MultiPolygon, Ring, multipolygon_area

TOLERANCE = 0.001  # 전체 면적 대비 허용 오차 (아키텍처 §7)
MAX_ITERATIONS = 200


def _clip_left(ring: Ring, x: float) -> Ring:
    # 반평면 X ≤ x로 자른다 (Sutherland–Hodgman). 오목한 링도 면적은 맞다
    clipped = []
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        inside1, inside2 = x1 <= x, x2 <= x
        if inside1:
            clipped.append((x1, y1))
        if inside1 != inside2:
            t = (x - x1) / (x2 - x1)
            clipped.append((x, y1 + t * (y2 - y1)))
    if len(clipped) < 3:
        return []
    return clipped + clipped[:1]


def area_left_of(polygons: MultiPolygon, x: float) -> float:
    clipped = []
    for polygon in polygons:
        rings = [_clip_left(ring, x) for ring in polygon]
        if rings[0]:
            clipped.append([ring for ring in rings if ring])
    return multipolygon_area(clipped)


def cut_positions(polygons: MultiPolygon, ratios: list[int]) -> list[float]:
    if not ratios or any(r <= 0 for r in ratios):
        raise ValueError("ratios must be positive")
    total = multipolygon_area(polygons)
    if total <= 0:
        raise ValueError("field has no area")

    # 큰 좌표(EPSG:5179 약 100만 m)에서 오차를 줄이려고 원점 근처로 옮겨 계산한다
    ox, oy = polygons[0][0][0]
    shifted = [[[(x - ox, y - oy) for x, y in ring] for ring in polygon] for polygon in polygons]
    xs = [x for polygon in shifted for x, _ in polygon[0]]
    max_x = max(xs)
    tolerance = TOLERANCE * total

    cuts = []
    lo = min(xs)
    for k in range(1, len(ratios)):
        target = total * sum(ratios[:k]) / sum(ratios)
        hi = max_x
        for _ in range(MAX_ITERATIONS):
            mid = (lo + hi) / 2
            area = area_left_of(shifted, mid)
            if abs(area - target) <= tolerance:
                break
            if area < target:
                lo = mid
            else:
                hi = mid
        else:
            raise RuntimeError("cut position did not converge")
        cuts.append(mid)
        lo = mid
    return [x + ox for x in cuts]
