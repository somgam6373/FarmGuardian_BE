# Zone split cut positions — `farm/domain/split.py` (design)

- Date: 2026-10-29
- Owner: Hyebin (farm context), part of issue #5
- Status: approved in chat (2026-10-29)
- Basis: `팜가디언_아키텍처.md` §7 「분할」, §9 tests. The first UI prototype (equal split only, 1–6 zones) is not a constraint; the architecture doc is.

## Intent

A field (farmmap parcels merged into one shape) is cut into zones by direction and ratios
(e.g. `[6, 4]`, or `[1, 1, 1]` for an equal split). The split APIs (`split-preview`, `zones`) need
a field stored in PostGIS (#4), so they come later. This piece is the part that needs no DB:
**where to cut so that each strip's area matches its ratio**.

Arch §7 pipeline, for context:
1. Rotate the field so its long side (from `ST_OrientedEnvelope`) lies on the x axis. `lengthwise`
   rotates a further 90° so the cut lines are still vertical. (PostGIS, later PR)
2. **`cut_positions(rings, ratios)` finds the x of each vertical cut line.** (this PR)
3. Cut each strip with `ST_Intersection`, rotate back. (PostGIS, later PR)

## Goal

`cut_positions(polygons: MultiPolygon, ratios: list[int]) -> list[float]` in `app/farm/domain/split.py`,
pure Python, no new dependency. (Arch §7 names the first parameter `rings`; this design takes the
`MultiPolygon` type from `geometry.py` so holes and several pieces are explicit — builder's call.)

- Input: the field shape **already rotated** (EPSG:5179 metres), in the `MultiPolygon` type of
  `farm/domain/geometry.py` (outer ring + holes per polygon, closed rings).
- Output: `len(ratios) - 1` x values, strictly increasing, left to right. Strip *k* is between cut
  *k-1* and cut *k* (the first strip starts at the field's min x, the last ends at its max x).
- Each cut *k* (1-based) satisfies: area of the field with `x ≤ cut_k` is within **0.1 % of the total
  area** of `total × sum(ratios[:k]) / sum(ratios)`.
- `ratios == [n]` (one zone) → `[]`.
- Deterministic: same input → same output (fixed bisection, no randomness).

## Non-goals

- Rotation, `ST_OrientedEnvelope`, `ST_Intersection`, building zone geometries (PostGIS, later PR).
- Request validation (1–10 positive ints, `zones` length) — the API layer's job (later PR).
- Re-split / merge (P1 per arch).

## Method (arch §7: half-plane clipping + shoelace)

- `area_left_of(polygons, x)`: clip every ring to the half-plane `X ≤ x` (Sutherland–Hodgman against
  one vertical line; works for concave rings — degenerate zero-width edges do not change the area),
  then `multipolygon_area` from `geometry.py` (holes subtracted).
- For each cut, bisect `x` over `[min_x, max_x]` of the outer rings until the left area is within the
  tolerance of the target. `area_left_of` is monotonic in `x`, so bisection converges. Search each
  cut from the previous cut's x.
- Concave fields: a strip may contain several pieces; that is fine (arch: one zone, MultiPolygon).

## Errors (builder's call)

`ValueError` for: empty `ratios`, a ratio ≤ 0, or a field with zero area. The API layer validates
first, so these are guards for programming mistakes, not user-facing errors.

## Tests (table-based pytest, arch §9)

Expected cut x computed by hand; assert with tolerance `0.001 × total area` on the left area (and
exact-ish x where the shape makes x obvious):

| Case | Shape | Ratios | Expected |
|---|---|---|---|
| Rectangle halves | 100 × 20 at origin | `[1, 1]` | `[50]` |
| 6:4 | 100 × 20 | `[6, 4]` | `[60]` |
| Thirds | 90 × 10 | `[1, 1, 1]` | `[30, 60]` |
| One zone | any | `[3]` | `[]` |
| L-shape | 0–100 × 0–10 plus 0–20 × 10–50 (area 1800) | `[1, 1]` | `[18]` (left area 50x for x ≤ 20) |
| Slanted (parallelogram) | (0,0) (100,0) (120,20) (20,20), area 2000 | `[1, 1]` | `[60]` (symmetric) |
| Hole | 100 × 20 with 20 × 10 hole at x 10–30 (area 1800) | `[1, 1]` | `[55]` (20x − 200 = 900) |
| Two pieces | squares 0–10 and 20–30 (y 0–10) | `[1, 1]` | left area 100 (any x in [10, 20] acceptable) |
| Determinism | same input twice | `[3, 2, 5]` | identical lists |
| Errors | `[]`, `[1, 0]`, zero-area field | — | `ValueError` |

## Left to the builder

Internal helper names, bisection iteration cap (must reach the tolerance on the test shapes),
whether tests assert x directly or the resulting left area.
