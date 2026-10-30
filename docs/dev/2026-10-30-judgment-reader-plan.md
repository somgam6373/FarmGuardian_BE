# Judgment Read Side Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three read functions, `last_judgments`, `recent_judgments` and `rotation`, that Hyebin's `GET /fields` and `GET /zones/{id}` call to fill `last_judgment`, `recent_judgments` and `rotation`, shaped exactly like API spec §2.

**Architecture:** New `app/judgment/application/reader.py` over two new SQL functions in `judgment/infrastructure/repository.py`. Names come from the static catalog; rotation reuses the domain `rotation_summary`. The spray-history conversion in `assess` becomes a public `service.spray_records` that `rotation` shares. No route, no farm file.

**Tech Stack:** Python 3.13, SQLAlchemy 2 `text()` SQL on psycopg 3, pytest against the PostGIS test database.

**Spec:** `docs/dev/2026-10-30-judgment-reader-design.md` (approved in chat 2026-10-30); frame = `docs/dev/팜가디언_API_명세.md` §1, §2 (never edited).

## Global Constraints

- `팜가디언_API_명세.md`, `schema.sql`, `requirements*.txt` and everything under `app/farm/` do not change; no route is added.
- `JudgmentBrief` = exactly `{judgment_id: int, created_at: datetime, pesticide: {id, name, item_name}, pest: {id, name} | None, verdict: str}`; `pesticide` has no `moa`. `created_at` is an aware `datetime` in `app.core.time.KST` with `microsecond=0` (wire form `2026-10-30T16:06:05+09:00`, spec §1). `verdict` is the stored string.
- `Rotation` = `{window_start: date | None, total: int, items: [{moa: {label_kr, system, code} | None, count: int}]}`, produced by `rotation_summary(...).model_dump()`.
- `recent_judgments`: newest first by `created_at DESC, id DESC`; default `limit=5` (spec §5). `last_judgments`: one SQL statement for any number of zones, zones without a judgment absent, `{}` for an empty list.
- A stored judgment whose pesticide or pest is not in the catalog is skipped without error (design decision 2); `last_judgments` then leaves that zone out and does not fall back to an older row.
- Layers: `reader` (application) calls `repository` (infrastructure), `catalog_service`, `spray_service` and `service.spray_records`; it never imports `farm` modules.
- Code and identifiers in English, short Korean comments like the surrounding code; ruff line length 100 (Korean counts double); tests flat in `tests/`; commit messages in English with the session's attribution trailer; do not push; stage explicit paths only (the working tree has an unrelated uncommitted backlog xlsx and `.gitignore` change).

## Review Focus

- `created_at` reaches the wire as `YYYY-MM-DDTHH:MM:SS+09:00`, never UTC or with microseconds. (Task 2)
- Order is newest first with the higher id first on equal times; `limit` applies; another zone's judgments never appear in a zone's list or last. (Tasks 2, 3)
- A judgment pointing at an id that left the catalog does not raise. (Tasks 2, 3)
- The home screen costs one statement however many zones it lists, and an empty zone list returns `{}`. (Task 3)
- Rotation with no sprays, and a spray exactly on `planted_at` (counts, `>=`). (Task 4)

---

### Task 0: Branch and commit the design and this plan

- [ ] **Step 1:** `git switch -c feat/jh-judgment-reader` (from `test` at `fe0e154`; the unrelated uncommitted files stay uncommitted).
- [ ] **Step 2:** `git add docs/dev/2026-10-30-judgment-reader-design.md docs/dev/2026-10-30-judgment-reader-plan.md` / `git commit -m "Add judgment reader design and plan"`.

### Task 1: Share the spray-history conversion

**Files:**
- Modify: `app/judgment/application/service.py`

**Interfaces:**
- Produces: `spray_records(history: Sequence[SprayView]) -> list[SprayRecord]` in `app/judgment/application/service.py`; the same list the `records = [...]` block in `assess` builds today (id, pesticide_id, item_name, sprayed_on, moa via `_moa`), order preserved.

- [ ] **Step 1:** Baseline: `pytest tests/test_judgment_assess.py tests/test_judgment_api.py tests/test_judgment_sweep.py -q` → all pass; note the count.
- [ ] **Step 2:** Move the inline comprehension out of `assess` into the public function above and call it from `assess` (no behavior change, no new test: the three files above are the safety net).
- [ ] **Step 3:** Same command → same count passes; `ruff check app/judgment` → `All checks passed!`.
- [ ] **Step 4:** `git add app/judgment/application/service.py` / `git commit -m "Extract spray_records from assess"`.

### Task 2: Recent judgments

**Files:**
- Modify: `app/judgment/infrastructure/repository.py`
- Create: `app/judgment/application/reader.py`
- Create: `tests/test_judgment_reader.py`

**Interfaces:**
- Consumes: `catalog_service.get_pesticide(id) -> Pesticide | None` (`.id .name .item_name`), `catalog_service.get_pest_card(id) -> PestCard | None` (`.id .name`), `KST` from `app.core.time`.
- Produces: `repository.recent(db, zone_id: int, limit: int) -> list[Row]` (columns `id, zone_id, pest_id, pesticide_id, verdict, created_at`, newest first); `reader.recent_judgments(db: Session, zone_id: int, limit: int = 5) -> list[dict]`; private `reader._brief(row) -> dict | None` (None when the pesticide or pest is not in the catalog), reused by Task 3.

- [ ] **Step 1: Write the failing tests** in `tests/test_judgment_reader.py`. Setup: `PEST = pests_with_drugs(1)[0]`, `DRUG = pool(1, PEST)[0]` (from `tests/judgment_scenarios.py`), `GONE = 2_000_000_000`; fixture `zone` (user, field, zone via `make_user`, `make_field`, `make_zone`) and `other_zone`; helper `add(db, zone_id, *, pest_id=None, pesticide_id=DRUG.id, verdict="OK", at=None) -> int` inserting into `judgment` (`apply_date` any date, `result` `'{}'::jsonb`, `created_at` = `COALESCE(:at, now())`) and returning the id. Tests:
  - `test_brief_has_exactly_the_spec_shape`: one row with `pest_id=PEST`, `verdict="CAUTION"` → keys `{judgment_id, created_at, pesticide, pest, verdict}`; `pesticide == {"id": DRUG.id, "name": DRUG.name, "item_name": DRUG.item_name}`; `pest == {"id": PEST, "name": get_pest_card(PEST).name}`; `verdict == "CAUTION"`; `judgment_id` is the inserted id.
  - `test_pest_is_null_when_none_was_given`.
  - `test_created_at_is_kst_seconds_on_the_wire`: `at=datetime(2026, 10, 30, 7, 6, 5, 123456, tzinfo=UTC)` → `brief["created_at"] == datetime(2026, 10, 30, 16, 6, 5, tzinfo=KST)` and `jsonable_encoder(brief)["created_at"] == "2026-10-30T16:06:05+09:00"`.
  - `test_newest_first_and_higher_id_first_on_equal_times`: three rows with times t1 < t3 and t2 in between inserted out of order, plus two rows with the same time → expected id order.
  - `test_default_limit_is_five_and_the_argument_applies`: 7 rows → 5 returned; `limit=2` → the 2 newest.
  - `test_other_zones_never_leak_and_an_empty_zone_is_empty`: rows only in `other_zone` → `[]` for `zone`.
  - `test_ids_that_left_the_catalog_are_skipped`: one row with `pesticide_id=GONE`, one with `pest_id=GONE`, one valid row → only the valid one comes back, no exception.
- [ ] **Step 2:** `pytest tests/test_judgment_reader.py -v` → FAIL (`ModuleNotFoundError: app.judgment.application.reader`).
- [ ] **Step 3: Implement** `repository.recent` (`ORDER BY created_at DESC, id DESC LIMIT :n`, filtered by `zone_id`), `reader._brief` (KST conversion `row.created_at.astimezone(KST).replace(microsecond=0)`) and `reader.recent_judgments` (rows → briefs, dropping `None`).
- [ ] **Step 4:** `pytest tests/test_judgment_reader.py -v` → all PASS; `ruff check app/judgment tests/test_judgment_reader.py` clean.
- [ ] **Step 5:** `git add app/judgment/infrastructure/repository.py app/judgment/application/reader.py tests/test_judgment_reader.py` / `git commit -m "Add recent_judgments reader"`.

### Task 3: Last judgment per zone

**Files:**
- Modify: `app/judgment/infrastructure/repository.py`, `app/judgment/application/reader.py`, `tests/test_judgment_reader.py`

**Interfaces:**
- Consumes: Task 2's `_brief`, `add`, `zone`, `other_zone`.
- Produces: `repository.latest_per_zone(db, zone_ids: list[int]) -> list[Row]` (same columns, one newest row per zone, `DISTINCT ON (zone_id)` ordered `zone_id, created_at DESC, id DESC`); `reader.last_judgments(db: Session, zone_ids: list[int]) -> dict[int, dict]`.

- [ ] **Step 1: Write the failing tests** (append):
  - `test_each_zone_gets_its_newest_judgment_and_empty_zones_are_absent`: two zones with several rows each (times out of order) plus a third zone with none → dict has exactly the first two keys, each value is that zone's newest brief.
  - `test_equal_times_pick_the_higher_id`.
  - `test_zones_not_asked_for_are_not_returned_and_an_empty_list_gives_empty_dict`.
  - `test_a_newest_row_with_a_stale_id_leaves_the_zone_out`: older valid row, newer row with `pesticide_id=GONE` → the zone is absent (no fallback).
  - `test_one_statement_for_many_zones`: count statements with `sqlalchemy.event.listen(db.get_bind(), "before_cursor_execute", ...)` around `last_judgments(db, [a, b, c])` → exactly 1; remove the listener afterwards.
- [ ] **Step 2:** `pytest tests/test_judgment_reader.py -v` → the five new tests FAIL (`AttributeError: module ... has no attribute 'last_judgments'`).
- [ ] **Step 3: Implement** `repository.latest_per_zone` (return `[]` without querying for an empty list) and `reader.last_judgments` (rows → `{row.zone_id: brief}` for the non-`None` briefs).
- [ ] **Step 4:** `pytest tests/test_judgment_reader.py -v` → all PASS; ruff clean.
- [ ] **Step 5:** `git add app/judgment/infrastructure/repository.py app/judgment/application/reader.py tests/test_judgment_reader.py` / `git commit -m "Add last_judgments reader"`.

### Task 4: Rotation

**Files:**
- Modify: `app/judgment/application/reader.py`, `tests/test_judgment_reader.py`

**Interfaces:**
- Consumes: `service.spray_records` (Task 1), `spray_service.history(db, zone_id) -> list[SprayView]`, `rules.rotation_summary(history, planted_at) -> RotationSummary`.
- Produces: `reader.rotation(db: Session, zone_id: int, planted_at: date | None) -> dict`.

- [ ] **Step 1: Write the failing tests** (append; helper `spray(db, zone_id, pesticide_id, day)` inserting into `spray_log` with `source='manual'` and a fresh `uuid4` request id, as in `tests/test_zone_summaries.py`; helper `two_moa_drugs()` returning two catalog pesticides with different `moa.label_kr`):
  - `test_no_sprays_gives_the_empty_rotation`: `rotation(db, zone, None) == {"window_start": None, "total": 0, "items": []}`.
  - `test_counts_sprays_per_moa_most_used_first`: drug A twice and drug B once → `total == 3`, `items` are `[{moa A, count 2}, {moa B, count 1}]` where each `moa` is a dict with exactly the keys `label_kr, system, code`.
  - `test_only_sprays_from_planting_on_count_and_the_planting_day_counts`: one spray before `planted_at`, one exactly on it, one after → `window_start == planted_at`, `total == 2`.
- [ ] **Step 2:** `pytest tests/test_judgment_reader.py -v` → the three new tests FAIL (`AttributeError` on `rotation`).
- [ ] **Step 3: Implement** `reader.rotation`: `rotation_summary(spray_records(spray_service.history(db, zone_id)), planted_at).model_dump()`.
- [ ] **Step 4:** `pytest tests/test_judgment_reader.py -v` → all PASS; ruff clean.
- [ ] **Step 5:** `git add app/judgment/application/reader.py tests/test_judgment_reader.py` / `git commit -m "Add rotation reader"`.

### Task 5: Verify the whole suite

- [ ] **Step 1:** `pytest -q -rs` → every test passes and none is skipped.
- [ ] **Step 2:** `ruff check .` → `All checks passed!`.
- [ ] **Step 3:** `git status -sb` shows only the two unrelated uncommitted files and the branch is 5 commits ahead of `origin/test`.
- [ ] **Step 4:** Report to the user: commands and output; the snippet Hyebin pastes (design doc, "Coordination"); that `JudgmentBrief` is still a 【결정】 shape to confirm with the frontend; and that push and PR wait for their word.
