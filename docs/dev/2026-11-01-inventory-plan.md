# Inventory (창고) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (project `CLAUDE.md`: implement in this session, step by step; no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax.

**Goal:** `POST|GET|DELETE /inventory` stores, per user, the catalog drugs they own (창고), so the app can badge and sort in-stock drugs across reloads and devices.

**Architecture:** A new `inventory` context (`application`, `infrastructure`, `presentation`; no `domain`, there are no rules to hold) over one new table. The catalog is static JSON, so ids are validated with `catalog_service.get_pesticide` and the table has no drug foreign key. Withdrawal is handled by the `users` foreign key cascade.

**Tech Stack:** FastAPI, SQLAlchemy raw SQL (`text`), PostgreSQL, pytest, ruff.

**Spec:** `docs/dev/2026-11-01-inventory-design.md` (approved 2026-11-01).

## Global Constraints

- Contract: `POST /inventory {drug_id: int}` → `201 {drug_id}` when added, `200 {drug_id}` when already there; `GET /inventory` → `200 [int]`, oldest added first; `DELETE /inventory/{drug_id}` → `204`, `404 NOT_FOUND` when not in this user's inventory. All three require `X-User-Id`.
- `drug_id` is the catalog drug id (`pesticide.id`). An id outside the catalog is `422 VALIDATION_ERROR` (`loc ["body","drug_id"]`, message 「알 수 없는 약제입니다」, type `value_error`) on `POST`, and `404` on `DELETE`, decided **before any database access** (a huge id would overflow the `int` column).
- Table (exact): `inventory(user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE, pesticide_id int NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(), PRIMARY KEY (user_id, pesticide_id))`. `clock_timestamp()`, not `now()`: rows added in one transaction must keep their order.
- Database changes are additive and approved for the dev (`DATABASE_URL`) and test (`TEST_DATABASE_URL`) databases only. Never print `.env` values; before running DDL print the database name only, and refuse a database whose name is neither the dev name nor ends with `_test`.
- Do not touch `app/farm/**`. Schema changes go in `schema.sql` only (no Alembic). Code and identifiers in English, user-facing strings in Korean. Ruff (`E,F,I`, line length 100) must pass.
- Commit steps run only when the user says so. Commit messages are English and end with the harness's `Co-Authored-By` trailer. Stage exact paths (two untracked docs under `docs/dev/` are not part of this work).

## Review Focus

Failure modes the design implies; each has a named test in the task that owns the code.

1. Ids outside the catalog (`0`, `-1`, `2**40`): `POST` 422 and `DELETE` 404 without reaching the database → Task 2 (`test_ids_outside_the_catalog_never_reach_the_database`), Task 3 (`test_post_rejects_bad_bodies_and_unknown_drugs`, `test_delete_unknown_and_huge_ids_are_404`).
2. A retried or doubled add: second `POST` is 200 and still one row → Task 2 (`test_add_is_idempotent_and_lists_in_added_order`), Task 3 (`test_post_is_201_then_200_and_stores_one_row`).
3. One user must never see or remove another's drugs → Task 2 (`test_users_are_isolated`), Task 3 (`test_inventories_are_per_user`).
4. Withdrawal leaves nothing behind → Task 3 (`test_withdrawal_removes_the_inventory`).
5. Malformed input: missing, `null`, non-numeric and fractional `drug_id`, a non-integer path segment → Task 3 (`test_post_rejects_bad_bodies_and_unknown_drugs`, `test_delete_with_a_non_integer_id_is_422`).

---

### Task 1: Table and databases

**Files:**
- Modify: `schema.sql`, `tests/test_schema_sql.py`
- Database: dev and test (one `CREATE TABLE` each)

**Interfaces:**
- Produces: table `inventory` exactly as in Global Constraints.

- [ ] **Step 1: Write the failing tests** in `tests/test_schema_sql.py`: add `"inventory"` to the expected set in `test_only_user_data_tables_and_crop_remain`; add `test_inventory_table_matches_the_schema_file` (uses the `db` fixture and `pg_catalog`/`information_schema` queries): columns are exactly `{user_id, pesticide_id, created_at}`; the primary key columns in order are `[user_id, pesticide_id]`; its one foreign key points at `users` with delete action cascade (`confdeltype == 'c'`); `column_default` of `created_at` contains `clock_timestamp`.
- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_schema_sql.py -v`. Expected: the set test FAILS (set mismatch) and the table test FAILS (table missing).
- [ ] **Step 3: Add the table to `schema.sql`** after the `judgment` index and before 「고정 데이터」, with a section comment 「창고 (사용자가 가진 약제)」 and the column comments from the design (`pesticide_id`: 정적 데이터의 약제 id, FK 없음; `created_at`: why `clock_timestamp()`).
- [ ] **Step 4: Apply to both databases.** One script run with the `.venv` Python: read `.env` with `dotenv_values`, take the `CREATE TABLE inventory (...)` statement out of `schema.sql` (regex), and for each of `DATABASE_URL` and `TEST_DATABASE_URL` open a SQLAlchemy engine, print only the database name, refuse as stated in Global Constraints, abort if `to_regclass('public.inventory')` is already not null, execute in one transaction, then check `to_regclass` is not null. Expected: two lines, one per database name, each ending `created`.
- [ ] **Step 5: Run** `pytest tests/test_schema_sql.py -v` (PASS) and `ruff check .`.
- [ ] **Step 6: Commit** `schema.sql tests/test_schema_sql.py` — `Add inventory table`.

### Task 2: Repository and service

**Files:**
- Create: `app/inventory/__init__.py`, `app/inventory/application/__init__.py`, `app/inventory/application/service.py`, `app/inventory/infrastructure/__init__.py`, `app/inventory/infrastructure/repository.py`
- Test: `tests/test_inventory_service.py`

**Interfaces:**
- Consumes: table (Task 1); `catalog_service.get_pesticide(pesticide_id: int) -> Pesticide | None`; `core.errors.AppError`.
- Produces (`repository`): `add(db: Session, user_id: int, pesticide_id: int) -> bool` (True when newly inserted), `remove(db, user_id, pesticide_id) -> bool` (True when a row was deleted), `list_ids(db, user_id) -> list[int]` (oldest first). None of them commits.
- Produces (`service`): `add_drug(db, user_id: int, drug_id: int) -> bool`, `remove_drug(db, user_id, drug_id) -> None`, `list_drugs(db, user_id) -> list[int]`. `add_drug` commits only when it added; `remove_drug` commits when it removed; errors as in Global Constraints (`remove_drug` raises `AppError("NOT_FOUND", 404, "찾을 수 없습니다")`).

- [ ] **Step 1: Write the failing tests** (`db`, `make_user` fixtures; real catalog ids from `catalog_service.all_pesticides()`):
  - `test_add_is_idempotent_and_lists_in_added_order`: add the larger id `b` first and the smaller id `a` second (so add order differs from id order) → `[True, True]`; adding `b` again → `False`; `list_drugs` equals `[b, a]` (added order, not id order).
  - `test_remove_deletes_one_row_and_404s_when_absent`: add two, remove one → list has the other; removing it again raises `AppError` with `status == 404`.
  - `test_users_are_isolated`: user A adds; user B's list is `[]`; B removing A's id raises 404; A's list is unchanged.
  - `test_ids_outside_the_catalog_never_reach_the_database` (parametrized `0`, `-1`, `2**40`): `add_drug(None, uid, id)` raises `AppError` with `status == 422` and `details["errors"][0]["loc"] == ["body", "drug_id"]`; `remove_drug(None, uid, id)` raises `AppError` with `status == 404` (passing `db=None` proves no database call: it would fail with `AttributeError`).
- [ ] **Step 2: Run** `pytest tests/test_inventory_service.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** the repository with raw SQL: `INSERT … ON CONFLICT DO NOTHING RETURNING pesticide_id` (a row back means added), `DELETE … RETURNING` for `remove`, `SELECT pesticide_id … ORDER BY created_at, pesticide_id` for `list_ids`; and the service functions as specified (follow `app/spraying/application/spray_service.py` for the unknown-drug error shape and for committing in the service).
- [ ] **Step 4: Run** `pytest tests/test_inventory_service.py -v` (PASS) and `ruff check .`.
- [ ] **Step 5: Commit** `app/inventory tests/test_inventory_service.py` — `Add inventory repository and service`.

### Task 3: Endpoints

**Files:**
- Create: `app/inventory/presentation/__init__.py`, `app/inventory/presentation/schemas.py`, `app/inventory/presentation/router.py`
- Modify: `app/main.py` (import and include the router after `spraying_router`)
- Test: `tests/test_inventory_api.py`

**Interfaces:**
- Consumes: `service.add_drug / remove_drug / list_drugs` (Task 2); `core.auth.current_user`.
- Produces: `InventoryIn(drug_id: int)`, `InventoryItem(drug_id: int)`; routes `POST /inventory` (`response_model=InventoryItem`, 201, the handler sets 200 when `add_drug` returns False), `GET /inventory` (`response_model=list[int]`), `DELETE /inventory/{drug_id}` (204). The router carries `dependencies=[Depends(current_user)]` like the other routers.

- [ ] **Step 1: Write the failing tests** (`client`, `make_user`, `db` fixtures; header `{"X-User-Id": str(uid)}`; `DRUG = catalog_service.all_pesticides()[0].id`):
  - `test_requires_authentication` (parametrized `post`, `get`, `delete`): `401 UNAUTHORIZED`.
  - `test_post_is_201_then_200_and_stores_one_row`: first `POST {"drug_id": DRUG}` → `201` body `{"drug_id": DRUG}`; the second → `200` same body; `SELECT count(*) FROM inventory WHERE user_id = :u` is 1.
  - `test_get_lists_ids_oldest_first`: add `b` then `a` (id order differs from add order) → `GET` is `[b, a]`; a user with nothing gets `[]`.
  - `test_post_rejects_bad_bodies_and_unknown_drugs` (parametrized: `{}`, `{"drug_id": null}`, `{"drug_id": "abc"}`, `{"drug_id": 1.5}`, `{"drug_id": 0}`, `{"drug_id": -5}`, `{"drug_id": 2**40}`): `422`, code `VALIDATION_ERROR`, `error.details.errors[0].loc == ["body", "drug_id"]`, and nothing stored.
  - `test_delete_is_204_then_404`: `DELETE` after a `POST` → `204` with no body; again → `404 NOT_FOUND`.
  - `test_delete_unknown_and_huge_ids_are_404` (parametrized `0`, `-1`, `2**40`): `404`.
  - `test_delete_with_a_non_integer_id_is_422`: `/inventory/abc` → `422 VALIDATION_ERROR`.
  - `test_inventories_are_per_user`: A adds; B's `GET` is `[]` and B's `DELETE` of that id is `404`; A's `GET` still has it.
  - `test_withdrawal_removes_the_inventory`: add a drug, `DELETE /me` → `204`; the count of `inventory` rows for that user is 0.
- [ ] **Step 2: Run** `pytest tests/test_inventory_api.py -v`. Expected: FAIL (404 for the routes).
- [ ] **Step 3: Implement** the schemas, the router (a thin layer over the service) and the registration in `app/main.py`.
- [ ] **Step 4: Run** `pytest tests/test_inventory_api.py tests/test_app.py -v` (PASS) and `ruff check .`.
- [ ] **Step 5: Commit** `app/inventory/presentation app/main.py tests/test_inventory_api.py` — `Add /inventory endpoints`.

### Task 4: Repository docs

**Files:**
- Modify: `docs/dev/팜가디언_API_명세.md`, `docs/dev/팜가디언_아키텍처.md`

- [ ] **Step 1: API spec.** Header and health-row "25개" → "28개"; owner table 준혁 (16) → (19) with the three endpoints; a 「창고」 section next to the spray endpoints with the contract from Global Constraints and a 【결정】 mark (the request left the response shape, ordering and error cases open; `drug_id` is the same number as `pesticide_id`); the `DELETE /me` text now also removes the inventory.
- [ ] **Step 2: Architecture doc.** Read §4, §5, §7 and the places that list tables or foreign keys, then add: the `inventory` context to the §4 tree (준혁); the table and its `users` cascade to §5; the three endpoints to the §7 API table. Match the surrounding Korean style; leave 혜빈님's descriptions alone.
- [ ] **Step 3: Commit** both files — `Document the inventory endpoints`.

### Task 5: Verification

- [ ] **Step 1: Full suite and lint.** `.venv/Scripts/python -m pytest -q` — Expected: all pass, none skipped (1203 before this work plus the new tests); `.venv/Scripts/python -m ruff check .` prints `All checks passed!`.
- [ ] **Step 2: Farm guard.** `git diff --stat test -- app/farm` prints nothing.
- [ ] **Step 3: Contract check on the real app.** Import `app.main.app` and print `app.openapi()["paths"]["/inventory"]` methods (`post`, `get`) and `["/inventory/{drug_id}"]` (`delete`). Expected: those three methods and no others.
- [ ] **Step 4: Report** the commands and output. Push and PR wait for the user's word. Outside this plan and the repo: the Notion 「API 명세서」 rows and pages for the three endpoints, a BE backlog row (my call: BE-56, S3, P0, 준혁), telling the frontend that `GET /crops` already exists (`?q=` ignored), and the open question about region statistics and OCR match reasons.
