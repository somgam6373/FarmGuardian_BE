# Fields (create, list, delete) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /fields`, `GET /fields`, `DELETE /fields/{id}`, a `create_field` function for signup, and `used_by_field_id` in `GET /parcels`.

**Architecture:** Raw `text()` SQL with PostGIS in a new `farm/infrastructure/field_repository.py`; zone summaries in a new `farm/application/zone_service.py`; orchestration (409 check → parallel Farmmap fetch → savepoint insert) in `farm/application/field_service.py`; Pydantic models and routes in `farm/presentation`. Auth from `app/core/auth.py`.

**Tech Stack:** Python 3.13 (venv 3.14), FastAPI, SQLAlchemy 2 `text()`, PostGIS, `httpx2`, `concurrent.futures.ThreadPoolExecutor`, pytest with the PostGIS test DB fixtures from `tests/conftest.py`.

**Spec:** `docs/dev/2026-10-29-fields-design.md`

## Global Constraints

- Branch `feat/hb-fields` (from `test` at `36e5ec5`). Commit messages in English, no AI attribution.
- Local test DB: `TEST_DATABASE_URL` → `farmguardian_test` (already in `.env`). DB tests must not be skipped when verifying.
- Errors (exact): 409 `AppError("PARCEL_ALREADY_USED", 409, "이미 다른 밭에 등록된 필지입니다", {"farmmap_ids": [...]})`; unknown id 422 `AppError("VALIDATION_ERROR", 422, "요청 값이 올바르지 않습니다", {"errors": [{"loc": ["body", "parcel_farmmap_ids", i], "msg": "팜맵에 없는 필지입니다", "type": "not_found"}, ...]})`; 404 and 401 come from `app/core/auth.py`; 502 comes from `farmmap.parcel_by_id`.
- Geometry out: GeoJSON `{"type": "MultiPolygon", "coordinates": ...}` only (no `crs`), 1 decimal; `area_m2` rounded to 1 decimal; `bbox` = `[minx, miny, maxx, maxy]`.
- Farmmap: at most 8 concurrent `parcel_by_id` calls, one shared `httpx2.Client(timeout=farmmap.TIMEOUT_SECONDS)`.
- `create_field` never commits. Routes commit.
- Other contexts only through their `application` services (exception already used by spraying: `catalog.presentation.schemas.pesticide_base` for the `Pesticide` shape).
- Ruff: line length 100, rules E/F/I. Comments in Korean, short, like the surrounding code.

## Review Focus

- Name of only spaces → 422, not a field named "   ". (Task 4: `test_blank_name_is_422`)
- Two parcels sharing an edge → field area equals the sum, geometry is one MultiPolygon. (Task 1: `test_adjacent_parcels_union_area`)
- One of several Farmmap calls fails (502) → nothing saved, no partial `field_parcel` rows. (Task 3: `test_upstream_error_saves_nothing`)
- After deleting a field, its parcels can be registered again. (Task 4: `test_deleted_field_frees_parcels`)
- `GET /parcels` with a wrong `X-User-Id` → 401; without it → unchanged and no DB needed. (Task 5)

---

### Task 1: Field repository (SQL)

**Files:**
- Modify: `app/farm/domain/geometry.py` (add `to_wkt`)
- Create: `app/farm/infrastructure/field_repository.py`
- Test: `tests/test_field_repository.py` (DB), `tests/test_farm_geometry.py` (add `to_wkt` test)

**Interfaces:**
- Produces:
  - `geometry.to_wkt(polygons: MultiPolygon) -> str` — `MULTIPOLYGON(((x y,...)),...)`.
  - `@dataclass(frozen=True) FieldRow(id: int, name: str, area_m2: float, geometry: dict, bbox: list[float])`
  - `used_farmmap_ids(db, user_id: int, farmmap_ids: list[str]) -> dict[str, int]` — farmmap_id → field_id, only this user's.
  - `insert_field(db, user_id: int, name: str, parcels: list[FarmmapParcel]) -> int` — inserts `field` (geom = `ST_Multi(ST_Union(...))` of the parcel WKTs, SRID 5179) and one `field_parcel` per parcel; returns field id. Does not commit, does not catch `IntegrityError`.
  - `list_fields(db, user_id: int) -> list[FieldRow]` (order by `id`), `get_field(db, field_id: int) -> FieldRow`.
  - `delete_field(db, field_id: int) -> None`.

- [ ] **Step 1: Write failing tests.** `to_wkt([[[(0,0),(1,0),(1,1),(0,0)]]]) == "MULTIPOLYGON(((0 0,1 0,1 1,0 0)))"`. DB tests (use `db`, `make_user`; a local helper `square(x0, size, farmmap_id)` builds a `FarmmapParcel` with `pnu="1"*19`, `lnm="1전"`, `land_use="밭"`, `vdpt_yr=2022`):
  - `test_adjacent_parcels_union_area`: squares 10×10 at x=0 and x=10 → `get_field(...).area_m2 == 200.0`, `geometry["type"] == "MultiPolygon"`, `"crs" not in geometry`, `len(geometry["coordinates"]) == 1`, `bbox == [0, 0, 20, 10]`.
  - `test_far_apart_parcels_stay_one_field`: x=0 and x=100 → 2 polygons, area 200.0.
  - `test_parcel_rows_saved`: `field_parcel` rows have the farmmap ids, pnu, lnm, land_use, vdpt_yr.
  - `test_used_farmmap_ids_only_mine`: another user's field with id `"1"` → not returned; mine → `{"1": field_id}`.
  - `test_duplicate_parcel_raises_integrity_error`: second `insert_field` with the same id for the same user raises `sqlalchemy.exc.IntegrityError`.
  - `test_list_fields_order_and_owner`, `test_delete_field_cascades_zone` (use `make_zone`; zone row gone after delete).
- [ ] **Step 2: Run** `pytest tests/test_field_repository.py tests/test_farm_geometry.py -v` → FAIL (import errors).
- [ ] **Step 3: Implement.** Geometry out via `ST_AsGeoJSON(geom, 1)` → `json.loads` → keep `type` and `coordinates`; area `round(ST_Area(geom), 1)`; bbox from `ST_XMin/YMin/XMax/YMax`. Pass all parcel WKTs as a `text[]` and union with `unnest`.
- [ ] **Step 4: Run** the same command → PASS (no skips).
- [ ] **Step 5: Commit** `Add field repository with PostGIS union`.

### Task 2: Zone summaries with last spray

**Files:**
- Create: `app/farm/application/zone_service.py`
- Test: `tests/test_zone_summaries.py` (DB)

**Interfaces:**
- Consumes: `spray_service.list_sprays(db, zone_id, limit=1)`, `catalog.presentation.schemas.pesticide_base`.
- Produces: `summaries(db, field_ids: list[int]) -> dict[int, list[dict]]` — field_id → zone summary dicts ordered by zone id, keys `id, name, crop {id, name}, planted_at, history_confirmed, area_m2, geometry, last_spray, last_judgment`. Fields without zones are missing from the dict (callers use `.get(id, [])`).

- [ ] **Step 1: Write failing tests** (`make_user`, `make_field`, `make_zone`; sprays inserted straight into `spray_log` with a real pesticide id from `catalog_service.list_pesticides(1)`):
  - `test_summary_shape`: keys exactly as above; `crop == {"id": 1, "name": "감자"}` (the `make_zone` crop is `min(id)`); `area_m2 == 100.0`; `last_spray is None`; `last_judgment is None`.
  - `test_last_spray_is_newest`: sprays on 2026-10-01 and 2026-10-05 → `last_spray["sprayed_on"] == date(2026, 10, 5)` and `last_spray["pesticide"]` has keys `id, name, item_name, moa`.
  - `test_groups_by_field_and_orders_by_id`: two fields, three zones → grouped, ascending ids; empty `field_ids` → `{}`.
- [ ] **Step 2: Run** `pytest tests/test_zone_summaries.py -v` → FAIL.
- [ ] **Step 3: Implement** one SQL query for the zones (join `crop`, `ST_AsGeoJSON(geom, 1)`, `ST_Area`), then `list_sprays` per zone. `last_spray` dict = `{"id", "pesticide": pesticide_base(view.pesticide).model_dump(), "sprayed_on", "source"}`. Comment that `last_judgment` waits for a judgment read service.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `Add zone summaries with last spray`.

### Task 3: Field service (create, list, delete)

**Files:**
- Modify: `app/farm/application/field_service.py`
- Test: `tests/test_field_service.py` (DB; Farmmap faked with `monkeypatch.setattr(farmmap, "parcel_by_id", fake)`)

**Interfaces:**
- Consumes: Task 1 repository, Task 2 `zone_service.summaries`, `farmmap.parcel_by_id(farmmap_id, *, client)`.
- Produces:
  - `create_field(db, user_id: int, name: str, farmmap_ids: list[str]) -> dict` — the `Field` dict (`zones: []`). Order: `used_farmmap_ids` → 409; fetch all in parallel → 422 not_found for every `None` (index in the request); then `with db.begin_nested(): insert_field(...)`, catching `IntegrityError` → 409 with the ids re-read by `used_farmmap_ids`. Never commits.
  - `list_fields(db, user_id: int) -> list[dict]` — `Field` dicts with `zones` from `summaries`.
  - `delete_field(db, field_id: int) -> None` — no commit.
  - Field dict keys: `id, name, area_m2, geometry, bbox, zones`.

- [ ] **Step 1: Write failing tests:**
  - `test_create_returns_field`: two adjacent fake squares → keys as above, `area_m2 == 200.0`, `zones == []`.
  - `test_already_used_is_409_before_farmmap`: an existing field holds `"1"`; request `["2", "1"]` → `AppError` code `PARCEL_ALREADY_USED`, `details == {"farmmap_ids": ["1"]}`, and the fake was never called.
  - `test_unknown_ids_are_422_with_indexes`: fake returns `None` for `"2"` and `"4"` in `["1","2","3","4"]` → `details["errors"]` locs `["body","parcel_farmmap_ids",1]` and `[...,3]`, `type == "not_found"`.
  - `test_upstream_error_saves_nothing`: fake raises the 502 `AppError` for one id → raised; `field` and `field_parcel` counts unchanged.
  - `test_race_on_insert_is_409`: monkeypatch `field_repository.used_farmmap_ids` to return `{}` on its first call only, with `"1"` already used → 409 with `["1"]`, and the session is still usable (`db.scalar(text("SELECT 1")) == 1`).
  - `test_at_most_8_concurrent_fetches`: fake records the peak number of in-flight calls (lock + counter + short `time.sleep`) for 20 ids → peak ≤ 8.
  - `test_list_fields_includes_zones`, `test_delete_field`.
- [ ] **Step 2: Run** `pytest tests/test_field_service.py -v` → FAIL.
- [ ] **Step 3: Implement** in `field_service.py` (`ThreadPoolExecutor(max_workers=8)` + `executor.map` keeps request order; one shared `httpx2.Client` passed as `client=`).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `Add field service for create, list and delete`.

### Task 4: `/fields` routes

**Files:**
- Modify: `app/farm/presentation/schemas.py`, `app/farm/presentation/router.py`
- Test: `tests/test_fields_api.py` (DB, `client`; Farmmap faked as in Task 3)

**Interfaces:**
- Consumes: Task 3 functions, `current_user`, `get_owned_field` (param `field_id`, so path `/fields/{field_id}`).
- Produces: schemas `FieldCreate(name, parcel_farmmap_ids)`, `Spray`-shaped `LastSpray`, `ZoneSummary`, `Field`. Validation: `name` stripped, 1–30 chars; ids each `^\d{1,30}$`, list 1–20, duplicates rejected by a validator. Routes: `POST /fields` 201 → `Field` (commit), `GET /fields` → `list[Field]`, `DELETE /fields/{field_id}` 204 (commit).

- [ ] **Step 1: Write failing tests:**
  - `test_requires_authentication` (parametrized over the 3 routes) → 401.
  - `test_create_201_and_list`: POST then GET → same field, `zones == []`.
  - `test_invalid_body_is_422` (parametrized): `[]`, 21 ids, `["1","1"]`, `[""]`, `["12a"]`, name `""`, name of 31 chars → 422 `VALIDATION_ERROR`, fake not called.
  - `test_blank_name_is_422`: name `"   "` → 422.
  - `test_unknown_id_is_422_not_found`, `test_used_parcel_is_409`, `test_other_users_parcel_is_fine`.
  - `test_delete_204_and_404s`: mine → 204 then GET empty; someone else's / unknown → 404.
  - `test_deleted_field_frees_parcels`: create with `"1"`, delete, create with `"1"` again → 201.
- [ ] **Step 2: Run** `pytest tests/test_fields_api.py -v` → FAIL.
- [ ] **Step 3: Implement** schemas and routes (`router.py` keeps `/parcels` and `/addresses/search` unauthenticated; add auth per route, not on the router).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `Add POST, GET and DELETE /fields`.

### Task 5: `used_by_field_id` in `GET /parcels`

**Files:**
- Modify: `app/farm/presentation/router.py`, `app/farm/application/field_service.py` (`find_parcels`)
- Test: `tests/test_parcels_api.py`

**Interfaces:**
- Consumes: `current_user` rules, `field_repository.used_farmmap_ids`.
- Produces: `optional_user(x_user_id: Header = None, db) -> int | None` in `router.py` (None without header, otherwise `current_user(x_user_id, db)`); `find_parcels(pnu: str, db=None, user_id: int | None = None) -> list[dict]`.

- [ ] **Step 1: Write failing tests** (existing tests stay unchanged and must still pass without a DB):
  - `test_used_by_field_id_with_header` (DB): a field of mine holds the fixture's first farmmap id → that parcel's `used_by_field_id == field_id`, others `None`.
  - `test_other_users_field_not_shown` (DB): same id in another user's field → `None`.
  - `test_bad_header_is_401` (DB): `X-User-Id: abc` and an unknown id → 401.
- [ ] **Step 2: Run** `pytest tests/test_parcels_api.py -v` → new tests FAIL.
- [ ] **Step 3: Implement** (no DB query when `user_id is None`).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `Fill used_by_field_id in GET /parcels`.

### Task 6: Verify and hand off

- [ ] **Step 1:** `pytest -q` → all pass, no skips from missing `TEST_DATABASE_URL`; `ruff check .` → clean.
- [ ] **Step 2:** Live check with `uvicorn` and the `dev` user (`python -m app.seed_demo --dev-user`): `POST /fields` with `["418203252100637"]` → 201 with `161-3전` area; `GET /parcels?pnu=4182032521101610003` with the header → that parcel's `used_by_field_id` set; `DELETE` → 204.
- [ ] **Step 3:** Update issue #4 checklist (models item dropped, `last_judgment` follow-up for Junhyeok) when opening the PR.
