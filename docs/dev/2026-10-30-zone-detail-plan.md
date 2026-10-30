# Zone detail and last judgment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill `last_judgment` in `GET /fields` and add `GET /zones/{zone_id}`.

**Architecture:** `zone_service` calls `app.judgment.application.reader` (application service, allowed by arch §4). Typed Pydantic models in `farm/presentation/schemas.py`.

**Tech Stack:** FastAPI, SQLAlchemy `text()`, pytest with the PostGIS test DB.

**Spec:** `docs/dev/2026-10-30-zone-detail-design.md`

## Global Constraints

- Branch `feat/hb-zone-detail`. English commits, no AI attribution. Ruff 100, E/F/I.

## Review Focus

- A judgment whose pesticide vanished from the catalog → reader drops it; `last_judgment` `null`, no 500. (Task 1: covered by reader; add one API assertion)
- Zone with no sprays → `rotation = {window_start: planted_at, total: 0, items: []}`. (Task 2)

---

### Task 1: `last_judgment` in zone summaries

**Files:** Modify `app/farm/application/zone_service.py` (`summaries`), `app/farm/presentation/schemas.py` (`JudgmentBrief`, `ZoneSummary.last_judgment: JudgmentBrief | None`); Test `tests/test_zone_summaries.py`, `tests/test_fields_api.py`.

- [ ] **Step 1: Tests:** helper `judge(db, zone_id, verdict, created_at)` inserting into `judgment` (`pest_id` NULL, real `pesticide_id`, `apply_date`, `result '{}'`). `test_last_judgment_is_newest`: two rows → newer verdict, keys `{judgment_id, created_at, pesticide, pest, verdict}`; existing `last_judgment is None` tests stay. API: `GET /fields` `last_judgment["created_at"]` ends with `+09:00`; unknown pesticide id → `null`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS. **Step 5: Commit** `Fill last judgment in zone summaries`.

### Task 2: `GET /zones/{zone_id}`

**Files:** Modify `app/farm/application/zone_service.py` (`zone_detail(db, zone_id) -> dict`), schemas (`RotationItem`, `Rotation`, `ZoneDetail(ZoneOut)`), router; Test `tests/test_zone_detail_api.py`.

- [ ] **Step 1: Tests:** 401; 404 other user's / unknown; keys = Zone keys + `rotation`, `recent_judgments`; no sprays → rotation `total 0, items []`, `window_start` = planted_at; two sprays with a moa → `total 2`, item `count 2`, moa keys `{label_kr, system, code}`; 6 judgments → 5 newest first.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS. **Step 5: Commit** `Add GET /zones/{zone_id}`.

### Task 3: Verify

- [ ] `pytest -q` all pass, `ruff check .` clean; live: create field + zones, run a judgment (`POST /zones/{id}/judgments`), check `GET /fields` and `GET /zones/{id}`; delete the field.
