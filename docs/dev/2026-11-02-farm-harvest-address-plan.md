# Farm part of the frontend integration — `harvest_at` and `address` (plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task in this session (CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Do Hyebin's two requested items (`팜가디언_혜빈님_요청_프론트연동.md` #1 and #3) so that Tasks 11 and 11b of `2026-11-02-frontend-integration-backend-plan.md` can run.

**Architecture:** `zone.harvest_at` and `field.address` are new nullable columns. Both are read and written inside `app/farm` only; `judgment` and `identity` consume them through the existing public functions (`zone_reader.get_zone_context`, `field_service.create_field`). No existing field changes meaning.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 (raw `text()` SQL), pydantic, pytest, ruff.

**Spec:** `2026-11-02-frontend-integration-design.md` (decisions 5 and 15, C1, B7, B11) and `팜가디언_혜빈님_요청_프론트연동.md` #1, #3. The Hyebin document is written in the voice of "준혁 does not edit `app/farm`"; this plan is the exception the user approved on 2026-11-02 ("너랑 내가 할거야"). Tell Hyebin before merging.

## Decisions to approve before starting

The request document left these as 「확인 필요」. The plan assumes the defaults below; change them now, not mid-build.

| # | Topic | Default in this plan |
|---|---|---|
| D1 | `harvest_at` vs `planted_at` | When both are set, `harvest_at >= planted_at` (same day allowed). Otherwise 422. A past `harvest_at` is allowed (the judgment shows a negative margin). No upper limit |
| D2 | Crop change | `crop_id` changes → `harvest_at` becomes null, like `planted_at` (new season), unless the same PATCH sends a `harvest_at` |
| D3 | `planted_at` changes alone | `harvest_at` stays. If the new `planted_at` is after it, rule D1 gives 422 |
| D4 | Where `harvest_at` is accepted | `PATCH /zones/{id}` only. `POST /fields/{id}/zones` (`ZoneSpec`) is unchanged, so new zones start with null |
| D5 | Error position for D1 | `loc ["body","harvest_at"]` when the request sent `harvest_at`, else `["body","planted_at"]` |
| D6 | `address` (#3) | Accepted (option B). `POST /fields` takes `address?`, stripped, 1–200 characters, blank or longer → 422 `loc ["body","address"]`. Existing fields: null. Not editable after creation (no `PATCH /fields`) |
| D7 | #4 split, #6 `plannedAt` | Both option A: the frontend adapts, no server change |
| D8 | Branch | Same branch `feat/frontend-integration-be` |

## Global Constraints

- This plan edits `app/farm` on purpose. After it, `git diff 69f502c -- app/farm` shows only the changes listed here. Nothing else under `app/farm` changes.
- Additive API changes only. `ZoneSpec`, `PesticideBase`, `LastSpray` stay as they are.
- Schema changes go in `schema.sql` only. Dev and test databases get `ALTER TABLE` by hand: `ALTER TABLE zone ADD COLUMN harvest_at date; ALTER TABLE field ADD COLUMN address text;` The user runs it on their databases; the throwaway container database `fg_test` is ours.
- Lint `ruff check .` (line length 100, E/F/I). Tests `python -m pytest -q` with `TEST_DATABASE_URL` set; the DB name must end in `_test`.
- Code and commit messages in English, comments in Korean like the surrounding code. Commit trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` and the `Claude-Session` line. Commit only with the user's go-ahead.
- Baseline before Task A: `1304 passed`, `ruff` clean.

## Review Focus

1. **PATCH merge logic**: crop change clearing `harvest_at`, an explicit `harvest_at` in the same request winning, `null` clearing it, and D1 evaluated on the *resulting* values (inside the `FOR UPDATE` read), not on the request alone.
2. **Unsent vs null**: `ZonePatch` uses "default None = not sent" for `name`, `crop_id`, `history_confirmed`; `harvest_at` must be clearable like `planted_at`, so `exclude_unset` is what distinguishes them.
3. **Every response that lists a zone** gets `harvest_at`: `ZoneOut` (create, patch), `ZoneDetail`, `ZoneSummary` in `GET /fields`. Missing one breaks the frontend silently.
4. **`harvest_at` change must not touch `history_confirmed`** (it does not affect the spray count window).
5. **`address` on every field response**: `POST /fields`, `GET /fields`, and signup (Task 11b) all go through `_field()`.

## Preflight

- [ ] `git status` clean on `feat/frontend-integration-be`; `python -m pytest -q` → 1304 passed; `ruff check .` clean.

---

### Task A: `zone.harvest_at` (request #1)

**Files:**
- Modify: `schema.sql` (`zone`), `app/farm/application/zone_service.py` (`summaries`, `get_zones`, `_zone`, `update_zone`), `app/farm/application/zone_reader.py` (`ZoneContext`, `get_zone_context`), `app/farm/presentation/schemas.py` (`ZoneSummary`, `ZoneOut`, `ZonePatch`)
- Test: `tests/test_zone_update.py`, `tests/test_zone_patch_api.py`, `tests/test_zone_summaries.py`, `tests/test_zone_detail_api.py`, `tests/test_zone_create.py`, `tests/test_zone_reader.py`, `tests/test_schema_sql.py`

**Interfaces:**
- Produces: `ZoneContext(crop_id, planted_at, history_confirmed, harvest_at: date | None = None)`; `ZoneOut.harvest_at`, `ZoneSummary.harvest_at: date | None`; `ZonePatch.harvest_at: date | None = None`; `update_zone(db, zone_id, changes, today)` accepts `changes["harvest_at"]`.
- Consumes (later, Task 11): `ZoneContext.harvest_at`.

- [ ] **Step 1: Write the failing tests.**

In `tests/test_zone_update.py` (use its `zone` fixture and `state` helper; add `harvest_at` to what `state` returns):

```python
def test_harvest_at_is_stored_and_can_be_cleared(db, zone):
    z = zone()
    assert zone_service.update_zone(db, z, {"harvest_at": date(2026, 9, 1)}, TODAY)["harvest_at"] == date(2026, 9, 1)
    assert zone_service.update_zone(db, z, {"harvest_at": None}, TODAY)["harvest_at"] is None

def test_harvest_at_may_equal_planted_at_but_not_precede_it(db, zone):
    z = zone(planted_at=MAY)
    assert zone_service.update_zone(db, z, {"harvest_at": MAY}, TODAY)["harvest_at"] == MAY
    with pytest.raises(AppError) as info:
        zone_service.update_zone(db, z, {"harvest_at": MAY - timedelta(days=1)}, TODAY)
    assert (info.value.status, info.value.details["errors"][0]["loc"]) == (422, ["body", "harvest_at"])

def test_a_past_harvest_date_is_allowed(db, zone):                      # D1: past is fine
    ...  # planted_at = MAY, harvest_at = MAY + 1 day, TODAY after both → no error

def test_crop_change_clears_harvest_at_unless_one_is_sent(db, zone):    # D2
    z = zone(); zone_service.update_zone(db, z, {"harvest_at": date(2026, 9, 1)}, TODAY)
    assert zone_service.update_zone(db, z, {"crop_id": OTHER_CROP}, TODAY)["harvest_at"] is None
    assert zone_service.update_zone(db, z, {"crop_id": FIRST_CROP, "harvest_at": date(2026, 10, 1)}, TODAY)["harvest_at"] == date(2026, 10, 1)

def test_planted_at_alone_keeps_harvest_at_and_a_later_planted_at_is_422(db, zone):   # D3, D5
    z = zone(planted_at=MAY); zone_service.update_zone(db, z, {"harvest_at": date(2026, 9, 1)}, TODAY)
    zone_service.update_zone(db, z, {"planted_at": date(2026, 6, 1)}, TODAY)           # still ≤ harvest_at
    with pytest.raises(AppError) as info:
        zone_service.update_zone(db, z, {"planted_at": date(2026, 9, 2)}, TODAY)
    assert info.value.details["errors"][0]["loc"] == ["body", "planted_at"]

def test_harvest_at_does_not_reset_the_confirmation(db, zone):          # Review Focus 4
    z = zone(confirmed=True)
    zone_service.update_zone(db, z, {"harvest_at": date(2026, 9, 1)}, TODAY)
    assert state(z).history_confirmed is True
```

In `tests/test_zone_patch_api.py`: add `harvest_at` to `ZONE_KEYS`; one API case that `PATCH {"harvest_at": "2026-09-01"}` → 200 with the value and `{"harvest_at": null}` clears it; a non-date string → 422 `loc ["body","harvest_at"]`. In `test_zone_summaries.py`, `test_zone_detail_api.py`, `test_zone_create.py`: add `harvest_at` to the key sets and assert it is `None` for a new zone. In `test_zone_reader.py`: a zone with `harvest_at` set by SQL gives `get_zone_context(...).harvest_at == that date`, and `None` otherwise. In `test_schema_sql.py`: `zone` has a `harvest_at` column (copy the `spray_log` columns check).

- [ ] **Step 2: Edit `schema.sql`:** add `harvest_at date,  -- 수확 예정일. NULL이면 ②는 수확 가능일만 보여 준다` to `zone`. Run on the container DB: `ALTER TABLE zone ADD COLUMN harvest_at date;` (the user runs it on theirs).
- [ ] **Step 3: Run** `python -m pytest tests/test_zone_update.py tests/test_zone_patch_api.py tests/test_zone_summaries.py tests/test_zone_detail_api.py tests/test_zone_create.py tests/test_zone_reader.py tests/test_schema_sql.py -q` → FAIL.
- [ ] **Step 4: Implement.**
  - `summaries()` and `get_zones()` select `z.harvest_at`; `summaries()` and `_zone()` put `"harvest_at": row.harvest_at` in the dict.
  - `ZoneSummary` and `ZoneOut` gain `harvest_at: date | None` (placed after `planted_at`); `ZoneDetail` inherits it.
  - `ZonePatch` gains `harvest_at: date | None = None` with the same comment as `planted_at` (it can be cleared with null).
  - `update_zone`: read `harvest_at` in the `FOR UPDATE` select; `harvest_at = current.harvest_at`; `if crop_id != current.crop_id: harvest_at = None`; `harvest_at = changes.get("harvest_at", harvest_at)`. After `planted_at` is final: `if planted_at and harvest_at and harvest_at < planted_at:` raise `AppError("VALIDATION_ERROR", 422, ..., {"errors": [{"loc": ["body", "harvest_at" if "harvest_at" in changes else "planted_at"], "msg": "수확 예정일은 정식일 이후여야 합니다", "type": "value_error"}]})`. Add `harvest_at = :harvest_at` to the `UPDATE`. Leave `confirmed` logic untouched.
  - `ZoneContext` gains `harvest_at: date | None = None`; `get_zone_context` selects it.
- [ ] **Step 5: Run** the same files plus `python -m pytest -q` and `ruff check .` → PASS.
- [ ] **Step 6: Commit** `feat(farm): add the zone harvest date`.

### Task C: `field.address` (request #3)

**Files:**
- Modify: `schema.sql` (`field`), `app/farm/infrastructure/field_repository.py` (`_FIELD_COLUMNS`, `FieldRow`, `_field`, `insert_field`), `app/farm/application/field_service.py` (`_field`, `create_field`), `app/farm/presentation/schemas.py` (`FieldCreate`, `FieldOut`), `app/farm/presentation/router.py` (`create_field`)
- Test: `tests/test_fields_api.py`, `tests/test_field_service.py`, `tests/test_field_repository.py`, `tests/test_schema_sql.py`

**Interfaces:**
- Produces: `create_field(db, user_id, name, farmmap_ids, address: str | None = None) -> dict` (the dict and `FieldOut` gain `address`); `FieldCreate.address: Address | None = None` where `Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]`; `FieldRow.address: str | None`.
- Consumed by Task 11b (identity signup).

- [ ] **Step 1: Write the failing tests.**

```python
# test_fields_api.py: FIELD_KEYS gains "address"
def test_address_is_saved_and_listed(client, ...):
    created = post_field(client, uid, address="  강원 평창군 대관령면 횡계리 1  ").json()
    assert created["address"] == "강원 평창군 대관령면 횡계리 1"
    assert [f["address"] for f in list_fields(client, uid).json()] == [created["address"]]

def test_address_is_optional_and_null_by_default(client, ...): ...

@pytest.mark.parametrize("value", ["", "   ", "가" * 201])
def test_blank_or_too_long_address_is_422(client, value):
    r = post_field(client, uid, address=value)
    assert (r.status_code, r.json()["error"]["details"]["errors"][0]["loc"]) == (422, ["body", "address"])

# test_field_service.py
def test_create_field_stores_the_address(db, make_user):
    field = field_service.create_field(db, make_user("farmer"), "앞밭", ["1"], address="평창군 1")
    assert field["address"] == "평창군 1"
    assert field_service.create_field(db, make_user("other"), "뒷밭", ["1"])["address"] is None
```

Reuse the farmmap/vworld fakes the existing tests in these files already use (do not add new fakes). `test_schema_sql.py`: `field` has an `address` column.

- [ ] **Step 2: Edit `schema.sql`:** add `address text,  -- 고른 주소(지번). NULL 허용` to `field`. Container DB: `ALTER TABLE field ADD COLUMN address text;`
- [ ] **Step 3: Run** the four test files → FAIL.
- [ ] **Step 4: Implement.** Add `address` to `_FIELD_COLUMNS`, `FieldRow`, `_field()` (repository); `insert_field(db, user_id, name, parcels, address=None)` inserts it (`INSERT INTO field (user_id, name, address, geom) SELECT :uid, :name, :address, ...`); `field_service._field()` returns `"address": row.address`; `create_field(..., address=None)` passes it; `FieldCreate`/`FieldOut` per Interfaces; the router passes `body.address`.
- [ ] **Step 5: Run** the four files, `python -m pytest -q`, `ruff check .` → PASS.
- [ ] **Step 6: Commit** `feat(farm): store the field address`.

### Task D: Documents and the Hyebin request status

**Files:**
- Modify: `docs/dev/팜가디언_API_명세.md` (§2 `Field`, `Zone`, `ZoneSummary`; §5 `POST /fields`, `PATCH /zones/{id}`), `docs/dev/팜가디언_아키텍처.md` (§5 `zone`, `field`; §8 address 「미정」), `docs/dev/팜가디언_혜빈님_요청_프론트연동.md` (status table), `docs/dev/2026-11-02-frontend-integration-design.md` (Status line), `docs/dev/2026-11-02-frontend-integration-backend-plan.md` (Tasks 11 and 11b: remove "BLOCKED", keep the grep checks)

- [ ] **Step 1: 명세:** `Field` and `ZoneSummary`/`Zone` get the new keys. `PATCH /zones/{id}`: `harvest_at?: date|null`, the D1–D3 rules and the 422 position (D5), marked **【결정】**. `POST /fields`: `address?` (D6). `ZoneSpec` unchanged (D4).
- [ ] **Step 2: 아키텍처:** §5 `zone(... planted_at, harvest_at, ...)`, `field(... name, address, ...)`; §8 「미정: 주소를 어느 응답에 넣을지」 → closed by `Field.address`, saved at `POST /fields` and signup.
- [ ] **Step 3: 혜빈 문서:** status table: #1 done, #3 accepted and done, #4 A, #6 A; add a line that 준혁 edited `app/farm` for #1 and #3 on 2026-11-02 with the commit ids.
- [ ] **Step 4: Commit** `docs: record the zone harvest date and field address`.

### Then, from the other plan

- Task 11 (judgment reads `ZoneContext.harvest_at`) and Task 11b (signup `field_address`): their stop condition is now met. Run them as written, then the closing checks of Task 12 (`pytest -q`, `ruff check .`).
- Report to the user: the `ALTER TABLE` statements for their databases, and that Hyebin must be told `app/farm` changed.
