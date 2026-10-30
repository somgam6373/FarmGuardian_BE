# Split preview and zone creation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /fields/{field_id}/split-preview` and `POST /fields/{field_id}/zones`, sharing one deterministic split.

**Architecture:** Rotation and strip geometry are pure Python in `farm/domain/split.py` (next to `cut_positions`). PostGIS gives the field geometry and its oriented envelope, and cuts the field with each strip (`ST_Intersection`). Strips are rotated rectangles built in the field's original frame, so only the strip is rotated and pieces are exact subsets of the field. Preview and create run the same SQL expression on the same strip WKT.

**Tech Stack:** Python 3.13 (venv 3.14), FastAPI, SQLAlchemy 2 `text()`, PostGIS 3.5, pytest with the PostGIS test DB fixtures.

**Spec:** `docs/dev/2026-10-30-zones-split-design.md`

## Global Constraints

- Branch `feat/hb-zones`, stacked on `feat/hb-fields` (PR #22). Commit messages in English, no AI attribution.
- `ratios`: 1–10 items, each int 1–100. `direction`: `"crosswise" | "lengthwise"`. `zones` length == `ratios` length; `name` stripped, 1–30 chars; `crop_id` must exist; `planted_at` optional date.
- Errors (exact): 409 `AppError("FIELD_ALREADY_SPLIT", 409, "이미 구역이 나뉜 밭입니다")`; unknown crop 422 `AppError("VALIDATION_ERROR", 422, "요청 값이 올바르지 않습니다", {"errors": [{"loc": ["body", "zones", i, "crop_id"], "msg": "없는 작물입니다", "type": "not_found"}, ...]})`; 404/401 from `get_owned_field` / `current_user`.
- Order: west→east, or south→north when pieces line up north-south (angle normalised to (−45°, 135°]).
- Output geometry: GeoJSON MultiPolygon 1 decimal without `crs`; `area_m2`, `bbox` 1 decimal (reuse `field_repository.geojson` and the rounding SQL style).
- Ruff line length 100, E/F/I. Short Korean comments.

## Review Focus

- Square field (long-side tie) → still deterministic, preview twice gives identical JSON. (Task 2: `test_square_field_is_deterministic`)
- Field whose long side runs north-south → crosswise order is south→north, not reversed. (Task 2: `test_vertical_field_order`)
- Field with two far-apart parcels → strips may cross the gap; each zone is a MultiPolygon and no zone is empty. (Task 2: `test_two_part_field`)
- Preview on a field that already has zones → allowed (read-only), create → 409. (Task 3/4)
- Pieces never overlap and sum to the field area. (Task 2: `test_pieces_cover_field`)

---

### Task 1: Pure split geometry

**Files:**
- Modify: `app/farm/domain/split.py`
- Test: `tests/test_farm_split.py`

**Interfaces:**
- Produces:
  - `long_side_angle(envelope: Ring) -> float` — radians in (−π/2, π/2]; longer of the first two edges (tie → first edge).
  - `rotate(polygons: MultiPolygon, angle: float, origin: tuple[float, float]) -> MultiPolygon` — counter-clockwise by `angle`.
  - `split_strips(polygons: MultiPolygon, envelope: Ring, direction: str, ratios: list[int]) -> list[Ring]` — one closed rectangle ring per ratio, in the **original** frame, ordered per Global Constraints. Algorithm: `θ = long_side_angle(envelope)`; frame angle `a = -θ` (crosswise) or `-(θ + π/2)` (lengthwise); origin = first envelope point; rotate field by `a`; `cuts = cut_positions(rotated, ratios)`; x bounds `[minx-1, *cuts, maxx+1]`, y bounds `miny-1 .. maxy+1`; each rectangle rotated back by `-a` about the same origin.

- [ ] **Step 1: Write failing tests:**
  - `test_long_side_angle`: envelope of a 20×10 axis rectangle starting at (0,0) → `0.0`; same listed starting from (20,10) going backwards → `0.0` (normalised); 10×20 → `pi/2`; rectangle at 30° → `radians(30)` (abs tol 1e-9).
  - `test_rotate_quarter_turn`: `rotate([[[(1,0),(2,0),(2,1),(1,0)]]], pi/2, (0,0))` ≈ `[[[(0,1),(0,2),(-1,2),(0,1)]]]`.
  - `test_strips_crosswise_rectangle`: 20×10 field, `[1,1]` → 2 rings; areas of `strip ∩ field` via `area_left_of` not needed — assert the first strip's max x ≈ 10 and it lies west of the second (min x of strip 1 < min x of strip 2).
  - `test_strips_lengthwise_rectangle`: 20×10, `[1,1]` → first strip's max y ≈ 5, south of the second.
  - `test_single_ratio_one_strip`: `[3]` → 1 ring covering the whole field bbox.
- [ ] **Step 2: Run** `pytest tests/test_farm_split.py -v` → new tests FAIL (import error).
- [ ] **Step 3: Implement** the three functions in `split.py` (pure, `math` only).
- [ ] **Step 4: Run** → PASS (old `cut_positions` tests too).
- [ ] **Step 5: Commit** `Add rotation and strip geometry for zone split`.

### Task 2: Split preview service

**Files:**
- Create: `app/farm/infrastructure/split_repository.py`
- Modify: `app/farm/application/field_service.py`
- Test: `tests/test_split_preview.py` (DB)

**Interfaces:**
- Consumes: Task 1 `split_strips`; `field_repository.geojson`; `geometry.to_wkt`.
- Produces:
  - `split_repository.field_shape(db, field_id) -> tuple[MultiPolygon, Ring]` — field geometry (full precision, e.g. `ST_AsGeoJSON(geom)`) and `ST_OrientedEnvelope(geom)` exterior ring.
  - `split_repository.PIECE_SQL` — SQL fragment `ST_Multi(ST_CollectionExtract(ST_Intersection(f.geom, ST_GeomFromText(:strip, 5179)), 3))` used by preview and by zone insert (Task 3).
  - `split_repository.preview(db, field_id, strips: list[str]) -> list[dict]` — `[{geometry, area_m2}]` in strip order.
  - `field_service.split_strips_for(db, field_id, direction, ratios) -> list[str]` (strip WKTs) and `field_service.split_preview(db, field_id, direction, ratios) -> list[dict]`.

- [ ] **Step 1: Write failing tests** (field via `field_repository.insert_field` with polygons built in the test; helper `field(db, uid, ring_or_polys)`):
  - `test_crosswise_rectangle`: 20×10 at origin, `[1,1]` → areas `[100.0, 100.0]`, piece 1 bbox max x ≈ 10 (west first).
  - `test_lengthwise_rectangle`: `[1,1]` → `[100.0, 100.0]`, piece 1 north edge ≈ 5 (south first).
  - `test_ratio_areas`: `[6,4]` → 120/80 within 0.2 ㎡.
  - `test_rotated_rectangle`: 30×10 rotated 30°, crosswise `[1,1,1]` → three ≈100 ㎡ pieces.
  - `test_vertical_field_order`: 10×20 (long side north-south), crosswise `[1,1]` → piece 1 south of piece 2.
  - `test_l_shape_ratios`: L-shaped field, `[1,1]` → each within 0.1 % of half the total.
  - `test_two_part_field`: squares at x=0 and x=100, `[1,1]` → both pieces non-empty, areas 100/100.
  - `test_pieces_cover_field`: sum of areas == field area within 0.1 %; pairwise `ST_Area(ST_Intersection(a, b)) < 0.01` (compute in SQL from the returned GeoJSON).
  - `test_square_field_is_deterministic` and `test_preview_twice_identical`: same output twice.
  - `test_single_ratio_is_whole_field`: `[3]` → one piece, area == field area.
- [ ] **Step 2: Run** `pytest tests/test_split_preview.py -v` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `Add split preview service`.

### Task 3: Zone creation service

**Files:**
- Modify: `app/farm/application/zone_service.py`, `app/farm/application/field_service.py`, `app/farm/infrastructure/split_repository.py`
- Test: `tests/test_zone_create.py` (DB)

**Interfaces:**
- Consumes: Task 2 `split_strips_for`, `PIECE_SQL`.
- Produces:
  - `zone_service.create_many(db, field_id: int, user_id: int, parts: list[dict]) -> list[dict]` — `parts` items `{name, crop_id, planted_at, strip}`; inserts in order; returns `Zone` dicts `{id, field_id, name, crop {id, name}, planted_at, history_confirmed, area_m2, geometry, bbox}`. No commit.
  - `field_service.create_zones(db, field_id, user_id, direction, ratios, zones: list[dict]) -> list[dict]` — locks the field (`SELECT 1 FROM field WHERE id = :id FOR UPDATE`), 409 if any zone exists, 422 for unknown crop ids (all of them, with index), then `create_many`. No commit.

- [ ] **Step 1: Write failing tests:**
  - `test_create_returns_zones_in_order`: 20×10, crosswise `[1,1]`, zones `감자`/`배추` (crop 1, 2), second with `planted_at=date(2026,3,1)` → keys as above, `crop == {"id": 2, "name": "배추"}` for the second, `history_confirmed is False`, areas 100/100, first is west.
  - `test_create_matches_preview`: geometries equal to `split_preview` output.
  - `test_already_split_is_409`: second create → `FIELD_ALREADY_SPLIT`, zone count unchanged.
  - `test_unknown_crop_is_422`: crop ids `[1, 999]` → loc `["body","zones",1,"crop_id"]`, `type "not_found"`, nothing inserted.
  - `test_field_list_shows_new_zones`: `field_service.list_fields` shows both zones.
- [ ] **Step 2: Run** `pytest tests/test_zone_create.py -v` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `Add zone creation from split`.

### Task 4: Routes, schemas, docs

**Files:**
- Modify: `app/farm/presentation/schemas.py`, `app/farm/presentation/router.py`, `docs/dev/팜가디언_API_명세.md` (§5 split-preview ratios line), `docs/dev/팜가디언_아키텍처.md` (§7 ratios line and the 「계산」 line: strips are rotated into the field's frame instead of rotating the field back — approved by Hyebin 2026-10-30)
- Test: `tests/test_zones_api.py` (DB)

**Interfaces:**
- Consumes: `field_service.split_preview`, `field_service.create_zones`, `get_owned_field`.
- Produces: `SplitRequest(direction: Literal[...], ratios: list[int 1–100], 1–10 items)`, `ZoneSpec(name stripped 1–30, crop_id: int, planted_at: date | None = None)`, `ZonesCreate(SplitRequest + zones: list[ZoneSpec])` with a length check, `SplitPiece`, `ZoneOut`. Routes `POST /fields/{field_id}/split-preview` (200) and `POST /fields/{field_id}/zones` (201, commit).

- [ ] **Step 1: Write failing tests:**
  - `test_requires_authentication` (both routes) → 401.
  - `test_preview_200_shape`: keys `{"geometry", "area_m2"}`, 2 items.
  - `test_invalid_split_is_422` (parametrized over both routes): direction `"diagonal"`, ratios `[]`, 11 items, `[0]`, `[-1]`, `[1.5]`, `[101]`.
  - `test_invalid_zones_is_422`: length mismatch, name `""`, `"   "`, 31 chars, missing `crop_id`.
  - `test_other_users_field_is_404_even_with_bad_body`.
  - `test_create_201_then_409` and `test_preview_allowed_after_split` (200).
  - `test_get_fields_shows_zones` after create.
  - Update the two doc lines: ratios "각 값은 1~100의 정수".
- [ ] **Step 2: Run** `pytest tests/test_zones_api.py -v` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `Add split-preview and zone creation routes`.

### Task 5: Verify

- [ ] **Step 1:** `pytest -q` all pass, no skips; `ruff check .` clean.
- [ ] **Step 2:** Live with the dev user: register the 2-parcel field (`418203252100637`, `418203252100655`), preview crosswise `[1,1]` and lengthwise `[6,4]`, create zones, `GET /fields` shows them; then delete the field.
