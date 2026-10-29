from app.farm.domain.geometry import MultiPolygon, Ring, multipolygon_area

# 허용 오차(전체 면적의 0.1%, 아키텍처 §7) 안에 들자마자 멈추지 않고 폭을 충분히 좁힌다.
# 100번 반으로 줄이면 float 정밀도 아래라 결과가 결정적이고 정확하다
ITERATIONS = 100


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

    cuts = []
    lo = min(xs)
    for k in range(1, len(ratios)):
        target = total * sum(ratios[:k]) / sum(ratios)
        hi = max_x
        for _ in range(ITERATIONS):
            mid = (lo + hi) / 2
            if area_left_of(shifted, mid) < target:
                lo = mid
            else:
                hi = mid
        cut = (lo + hi) / 2
        cuts.append(cut)
        lo = cut
    return [x + ox for x in cuts]
