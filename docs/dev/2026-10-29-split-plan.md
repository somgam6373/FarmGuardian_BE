# Zone split cut positions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `cut_positions(polygons, ratios)` in `app/farm/domain/split.py` returns the x of each vertical cut so strip areas match the ratios within 0.1 % of the total area.

**Architecture:** Pure domain function next to `geometry.py`: clip rings to the half-plane `X ≤ x` (Sutherland–Hodgman against one vertical line), reuse `multipolygon_area`, bisect each cut. No DB, no new dependency.

**Tech Stack:** Python 3.13 (venv 3.14), pytest.

**Spec:** `docs/dev/2026-10-29-split-design.md`

## Global Constraints

- Branch `feat/hb-split` (stacked on `feat/hb-parcels`). Commit messages in English.
- Input type `MultiPolygon` from `app/farm/domain/geometry.py` (closed rings; first ring outer, rest holes).
- Tolerance: `0.001 × total area` on the cumulative left area of each cut.
- Output: `len(ratios) - 1` floats, strictly increasing; `[]` for one ratio. Deterministic.
- `ValueError` for empty ratios, a ratio ≤ 0, zero-area field.
- Ruff line length 100, rules E/F/I; short Korean comments like `geometry.py`.

## Review Focus

- Cut line passing exactly through a vertex or along a vertical edge (rectangle edges at the cut x) → area still correct, no duplicate/degenerate crash. (Task 1)
- Field far from the origin (EPSG:5179 coordinates ~ 990000, 1970000) → same cuts as the shifted shape, tolerance met (float precision). (Task 1)
- Very uneven ratios (`[1, 9]`, `[1, 1, 8]`) → each cut within tolerance. (Task 1)
- Ring given clockwise vs counter-clockwise → same result. (Task 1)
- Ten equal parts (`[1] * 10`) → 9 strictly increasing cuts. (Task 1)

---

### Task 1: `cut_positions`

**Files:**
- Create: `app/farm/domain/split.py`
- Test: `tests/test_farm_split.py`

**Interfaces:**
- Consumes: `MultiPolygon`, `Ring`, `multipolygon_area` from `app/farm/domain/geometry.py`.
- Produces: `area_left_of(polygons: MultiPolygon, x: float) -> float`; `cut_positions(polygons: MultiPolygon, ratios: list[int]) -> list[float]`.

- [ ] **Step 1: Write failing tests** — helper `rect(x0, y0, x1, y1) -> Polygon` (closed ring); helper `assert_cuts(polygons, ratios)` that checks every cut's `area_left_of` against `total × cumulative ratio` within `0.001 × total`.

```python
@pytest.mark.parametrize("polygons, ratios, expected", [
    ([rect(0, 0, 100, 20)], [1, 1], [50]),
    ([rect(0, 0, 100, 20)], [6, 4], [60]),
    ([rect(0, 0, 90, 10)], [1, 1, 1], [30, 60]),
    (L_SHAPE, [1, 1], [18]),                 # rect(0,0,100,10) + rect(0,10,20,50) as one ring
    (PARALLELOGRAM, [1, 1], [60]),           # (0,0) (100,0) (120,20) (20,20)
    (WITH_HOLE, [1, 1], [55]),               # rect(0,0,100,20) with hole rect(10,5,30,15)
])
def test_known_cuts(polygons, ratios, expected):   # each cut ≈ expected within 0.001 × width; assert_cuts holds
def test_one_zone_has_no_cut():                      # [3] → []
def test_two_pieces_cut_in_the_gap():                # [rect(0,0,10,10), rect(20,0,30,10)], [1,1] → one cut, 9.99 ≤ x ≤ 20.01
def test_deterministic():                            # same input twice with [3, 2, 5] → identical lists
def test_area_left_of():                             # rect(0,0,100,20): x=-5 → 0, x=25 → 500, x=200 → 2000; WITH_HOLE x=20 → 300
def test_far_from_origin():                          # rect shifted by (990000, 1970000), [6, 4] → assert_cuts holds, cut ≈ 990060
def test_clockwise_ring():                           # reversed ring of rect → same cuts as counter-clockwise
@pytest.mark.parametrize("ratios", [[1, 9], [1, 1, 8], [1] * 10])
def test_uneven_and_many_ratios(ratios):             # on L_SHAPE: assert_cuts holds, cuts strictly increasing, len == len(ratios) - 1
@pytest.mark.parametrize("polygons, ratios", [([rect(0,0,10,10)], []), ([rect(0,0,10,10)], [1, 0]), ([rect(0,0,0,10)], [1, 1])])
def test_invalid_input_raises(polygons, ratios):     # ValueError
```

- [ ] **Step 2:** `pytest tests/test_farm_split.py -q` → FAIL (import error)
- [ ] **Step 3:** Implement in `split.py`: `_clip_left(ring, x)` (Sutherland–Hodgman against `X ≤ x`, returns a closed ring or `[]`), `area_left_of`, `cut_positions` (bisection between previous cut and the outer rings' max x; stop when within tolerance; iteration cap 200 then raise `RuntimeError` — unreachable for valid input).
- [ ] **Step 4:** `pytest -q` → all PASS; `ruff check .` clean
- [ ] **Step 5:** Commit `Add cut position search for zone split`
