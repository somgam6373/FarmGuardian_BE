from math import atan2, cos, hypot, pi, sin

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


def long_side_angle(envelope: Ring) -> float:
    """최소 회전 사각형의 긴 변 각도 (라디안, -π/2 초과 π/2 이하). 같으면 첫 변."""
    (x0, y0), (x1, y1), (x2, y2) = envelope[:3]
    first, second = (x1 - x0, y1 - y0), (x2 - x1, y2 - y1)
    dx, dy = second if hypot(*second) > hypot(*first) else first
    angle = atan2(dy, dx)
    # 방향을 동쪽(세로면 북쪽)으로 맞춰 순서가 밭마다 뒤집히지 않게 한다
    if angle <= -pi / 2:
        angle += pi
    elif angle > pi / 2:
        angle -= pi
    return angle


def rotate(polygons: MultiPolygon, angle: float, origin: tuple[float, float]) -> MultiPolygon:
    """origin을 중심으로 반시계 방향 angle만큼 돌린다."""
    ox, oy = origin
    c, s = cos(angle), sin(angle)
    return [
        [
            [(ox + (x - ox) * c - (y - oy) * s, oy + (x - ox) * s + (y - oy) * c) for x, y in ring]
            for ring in polygon
        ]
        for polygon in polygons
    ]


def split_strips(
    polygons: MultiPolygon, envelope: Ring, direction: str, ratios: list[int]
) -> list[Ring]:
    """밭을 자를 띠(직사각형)들. 원래 좌표계이며 crosswise는 서→동, lengthwise는 남→북 순서."""
    angle = long_side_angle(envelope)
    if direction == "lengthwise":
        angle += pi / 2
    # 자르는 방향이 x축이 되게 돌린 좌표계에서 세로선으로 자른다
    origin = envelope[0]
    rotated = rotate(polygons, -angle, origin)
    points = [point for polygon in rotated for point in polygon[0]]
    min_x, max_x = min(x for x, _ in points), max(x for x, _ in points)
    min_y, max_y = min(y for _, y in points) - 1, max(y for _, y in points) + 1
    edges = [min_x - 1, *cut_positions(rotated, ratios), max_x + 1]
    strips = [
        [(x0, min_y), (x1, min_y), (x1, max_y), (x0, max_y), (x0, min_y)]
        for x0, x1 in zip(edges, edges[1:])
    ]
    # 밭이 아니라 띠를 원래 각도로 돌린다 (밭 도형은 그대로 두고 자른다)
    return [ring for [[ring]] in (rotate([[strip]], angle, origin) for strip in strips)]
