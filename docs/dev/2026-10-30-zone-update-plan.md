# Zone update and centroid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `PATCH /zones/{zone_id}`, `zone_service.centroid_wgs84`, and a future-planting-date check for zone creation and update.

**Architecture:** Rules live in `farm/application/zone_service.py` (read current row, apply crop → date → confirmation rules, `UPDATE`, return `get_zones`). `today` is injected by routes from `today_kst()`. Request models in `farm/presentation/schemas.py`; explicit `null` vs omitted is read from `model_fields_set`.

**Tech Stack:** Python 3.13 (venv 3.14), FastAPI, SQLAlchemy 2 `text()`, PostGIS, pytest with the PostGIS test DB.

**Spec:** `docs/dev/2026-10-30-zone-update-design.md`

## Global Constraints

- Branch `feat/hb-zone-detail` (stacked on `feat/hb-zones`). English commits, no AI attribution.
- Future date error item: `{"loc": [...,"planted_at"], "msg": "정식일은 오늘 이후일 수 없습니다", "type": "value_error"}`; unknown crop item: `{"loc": [..., "crop_id"], "msg": "없는 작물입니다", "type": "not_found"}`; both inside `AppError("VALIDATION_ERROR", 422, "요청 값이 올바르지 않습니다", {"errors": [...]})`.
- "Future" = `planted_at > today` (today itself is allowed).
- Ruff line length 100, E/F/I. Short Korean comments.

## Review Focus

- `planted_at` equal to today → accepted. (Task 1, Task 2)
- PATCH with `{"planted_at": null}` on a zone whose date is already `null` → no change, confirmation kept. (Task 2)
- PATCH that changes crop and sends `history_confirmed: true` → new date `null`, confirmation `true`. (Task 2)
- PATCH body `{}` → 200, zone unchanged. (Task 3)
- `centroid_wgs84` returns `lon` first-named but callers use attributes; values in Korea's range for real coordinates. (Task 4)

---

### Task 1: Future planting date in zone creation

**Files:** Modify `app/farm/application/field_service.py` (`create_zones` gains `today: date`), `app/farm/presentation/router.py` (pass `today_kst()`); Test `tests/test_zone_create.py`, `tests/test_zones_api.py`.

**Interfaces:** Produces `create_zones(db, field_id, user_id, direction, ratios, zones, today: date)`; unknown crops and future dates collected into one `errors` list (zone order, crop before date within a zone), after the 409 check.

- [ ] **Step 1: Tests:** existing service calls pass `today=date(2026, 10, 30)`; `test_future_planted_at_is_422`: zone 1 `planted_at=date(2026, 10, 31)` → loc `["body","zones",1,"planted_at"]`, nothing inserted; `test_today_planted_at_is_ok`: `date(2026, 10, 30)` → created; `test_crop_and_date_errors_together`: zone 0 unknown crop, zone 1 future date → 2 errors in that order. API: `test_future_planted_at_api_is_422` with tomorrow KST.
- [ ] **Step 2: Run** `pytest tests/test_zone_create.py tests/test_zones_api.py -q` → new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `Reject future planting dates in zone creation`.

### Task 2: Zone update service

**Files:** Modify `app/farm/application/zone_service.py`; Test `tests/test_zone_update.py` (DB).

**Interfaces:** Consumes `split_repository.existing_crop_ids`, `get_zones`. Produces `update_zone(db, zone_id: int, changes: dict, today: date) -> dict` — `changes` holds only the keys the client sent (`name`, `crop_id`, `planted_at`, `history_confirmed`); returns the `Zone` dict. No commit.

- [ ] **Step 1: Tests** (zone via `make_zone`; set a starting state with SQL: crop 1, `planted_at` 2026-05-01, confirmed `true` unless stated), table-driven where possible:
  - rename only → name changed, rest same.
  - `{"crop_id": 2}` → crop 2, date `None`, confirmed `False`.
  - `{"crop_id": 2, "planted_at": date(2026, 9, 1)}` → that date, confirmed `False`.
  - `{"crop_id": 2, "history_confirmed": True}` → date `None`, confirmed `True`.
  - `{"crop_id": 1}` (same crop) → date and confirmation unchanged.
  - `{"planted_at": date(2026, 6, 1)}` → confirmed `False`; with `history_confirmed: True` → `True`.
  - `{"planted_at": date(2026, 5, 1)}` (same) → confirmed stays `True`.
  - `{"planted_at": None}` → date `None`, confirmed `False`.
  - starting date `None`, confirmed `True`: `{"crop_id": 2}` → confirmed stays `True`; `{"planted_at": None}` → stays `True`.
  - `{"history_confirmed": False}` → `False`.
  - `{"planted_at": today}` OK; `{"planted_at": today + 1 day}` → 422 loc `["body","planted_at"]`; `{"crop_id": 999, "planted_at": tomorrow}` → 2 errors (crop, then date); nothing changed after a 422.
- [ ] **Step 2: Run** `pytest tests/test_zone_update.py -q` → FAIL.
- [ ] **Step 3: Implement** (read `crop_id, planted_at, history_confirmed, name` of the zone, apply rules, one `UPDATE`).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `Add zone update rules`.

### Task 3: `PATCH /zones/{zone_id}` route and docs

**Files:** Modify `app/farm/presentation/schemas.py` (`ZonePatch`), `app/farm/presentation/router.py`, `docs/dev/팜가디언_API_명세.md` (§5 zone creation + PATCH: 「`planted_at`은 오늘(KST) 이후 불가」); Test `tests/test_zone_patch_api.py` (DB).

**Interfaces:** `ZonePatch(name: Name | None = None, crop_id: int | None = None, planted_at: date | None = None, history_confirmed: bool | None = None)` with an after-validator rejecting explicit `null` for `name`, `crop_id`, `history_confirmed`; route passes `body.model_dump(exclude_unset=True)` and `today_kst()`, uses `get_owned_zone`, commits, returns `ZoneOut`.

- [ ] **Step 1: Tests:** 401 without header; 404 for another user's zone even with body `{"name": null}`; `{}` → 200 unchanged; rename → 200 `ZoneOut` keys; `{"planted_at": null}` clears; 422 for `{"name": null}`, `{"crop_id": null}`, `{"history_confirmed": null}`, `{"name": "   "}`, 31-char name, unknown crop, tomorrow KST.
- [ ] **Step 2: Run** `pytest tests/test_zone_patch_api.py -q` → FAIL.
- [ ] **Step 3: Implement** + doc lines.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `Add PATCH /zones/{zone_id}`.

### Task 4: `centroid_wgs84`

**Files:** Modify `app/farm/application/zone_service.py`; Test `tests/test_zone_centroid.py` (DB).

**Interfaces:** `@dataclass(frozen=True) WgsPoint(lon: float, lat: float)`; `centroid_wgs84(db, zone_id: int) -> WgsPoint`; unknown zone → `AppError("NOT_FOUND", 404, "찾을 수 없습니다")`.

- [ ] **Step 1: Tests:** a zone whose geometry is a 10×10 square around EPSG:5179 `(993840, 1970360)` (Hyebin's real field area) → equals `ST_Transform(ST_SetSRID(ST_Point(993845, 1970365), 5179), 4326)` within 1e-9, and `126 < lon < 130`, `33 < lat < 39`; unknown id → 404.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `Add zone centroid in WGS84 for weather`.

### Task 5: Verify

- [ ] `pytest -q` all pass, no skips; `ruff check .` clean.
- [ ] Live with the dev user: create field + zones, `PATCH` crop change and date change, check `GET /fields`, then delete the field.
