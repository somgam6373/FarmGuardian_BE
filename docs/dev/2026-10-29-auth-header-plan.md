# X-User-Id Auth Dependencies Implementation Plan (BE-15)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FastAPI dependencies `current_user`, `get_owned_field`, `get_owned_zone` that authenticate by the `X-User-Id` header and enforce ownership in one place, plus the `dev` seed user and the real-PostGIS test fixtures the API tests need.

**Architecture:** One new file `app/core/auth.py` with three sync dependencies that query `users` / `field` / `zone` through `sqlalchemy.text` (no ORM models exist yet; other contexts' tables are read by raw SQL, never by importing their code). Errors reuse `AppError` (401 `UNAUTHORIZED`, 404 `NOT_FOUND`). `tests/conftest.py` gains a per-test-rollback session on the test DB. `app/seed_demo.py --dev-user` creates the `dev` user.

**Tech Stack:** Python 3.13, FastAPI `Depends`/`Header`, SQLAlchemy 2 (`text`, savepoint-joined test session), psycopg 3, pytest + `TestClient`, `python-dotenv` (already installed via pydantic-settings).

**Spec:** `docs/dev/팜가디언_아키텍처.md` §9 (인증 / 테스트 / 개발용 사용자), `docs/dev/팜가디언_API_명세.md` §1 (공통, 오류 응답). Backlog row BE-15.

## Global Constraints

- "`X-User-Id: {id}` 헤더 (정수). 없거나 없는 사용자면 401." "남의 밭·구역·기록은 **404** `NOT_FOUND`." (API spec §1)
- Error body is `{"error": {"code", "message", "details?"}}`; `UNAUTHORIZED` and `NOT_FOUND` carry no `details`. (API spec §1)
- "헤더가 없거나 사용자가 없으면(탈퇴) 401. 보안은 최소로 한다 (시연용)." The 4 auth-free APIs (`POST /auth/signup`, `POST /auth/login`, `GET /addresses/search`, `GET /parcels`) simply do not use these dependencies.
- API tests: "`TestClient` + **실제 PostGIS 테스트 DB**… 테스트마다 트랜잭션 롤백." (arch §9)
- Dev user: id `dev`, "`python -m app.seed_demo --dev-user`", "밭·구역 없이 사용자만". (arch §9)
- Code and identifiers in English; short Korean comments as in `app/core`. Ruff line length 100, rules E/F/I. Tests are flat files in `tests/`.
- Table/column names come from `schema.sql` (`users(id, username, password_hash)`, `field(id, user_id)`, `zone(id, user_id)`; `zone.user_id` is a copy kept equal to the field's by a composite FK).

## Calls made beyond the spec (check these)

1. Dependencies live in `app/core/auth.py`, use raw `text()` SQL, and return a plain `int` (`current_user` → user id; the owned checks → the field/zone id).
2. A present-but-malformed `X-User-Id` (`abc`, `0`, `01`, `-1`, `1.5`, 19 digits…) is **401**, not 422 — same body as missing. Accepted format: `[1-9][0-9]{0,17}` (ASCII digits only).
3. Messages: 401 `"인증이 필요합니다"`, 404 `"찾을 수 없습니다"`. Other-user's resource and non-existent resource return the identical 404 body. The header value is never echoed.
4. Routes must name the path parameters `field_id` / `zone_id` (the dependencies read them from the path). Noted in the architecture doc.
5. `dev` user's `password_hash` is the locked value `'!'` (no password can match; `dev` is header-only). BE-17's login must treat `'!'` as "no match" without crashing.
6. `tests/conftest.py` now **forces** `DATABASE_URL` to `TEST_DATABASE_URL` (from env or `.env`) so tests can never touch the dev DB; with no `TEST_DATABASE_URL`, DB tests are **skipped**, the rest still run. The `db` fixture refuses a database whose name does not end in `_test`.
7. Branch `feat/jh-auth-header` is stacked on `feat/jh-db-setup` (the `test` branch lacks the `schema.sql`-only doc changes; both edit `팜가디언_아키텍처.md` near line 318). Merge db-setup first.

## Review Focus

- Malformed header (`abc`, `0`, `-1`, `1.5`, `1_0`, 19 digits, non-ASCII digits) → 401, never 422/500. (Task 2)
- Header of a deleted (withdrawn) user, or an 18-digit id that never existed → 401. (Task 2)
- Another user's field/zone → 404 with a body identical to a non-existent id (no existence leak). (Task 3)
- No header on a non-existent resource → 401, not 404 (auth runs before lookup). (Task 3)
- Out-of-range path ids (`0`, `-1`, `10**20`) → 404, never 500; non-integer id → 422. (Task 3)

---

### Task 0: Environment and plan commit

- [ ] **Step 1:** Add `TEST_DATABASE_URL` to `.env.example` (after `FARMMAP_API_KEY`), with a comment line above it saying DB tests use it, the name must end in `_test`, and DB tests are skipped when it is unset:
  `TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/farmguardian_test`
- [ ] **Step 2 (user):** add the same line to the local `.env` with the real password (never paste it in chat).
- [ ] **Step 3:** Verify: `.venv\Scripts\python -c "from dotenv import dotenv_values; from sqlalchemy.engine import make_url; print(make_url(dotenv_values('.env')['TEST_DATABASE_URL']).database)"` — Expected: `farmguardian_test`.
- [ ] **Step 4:** Commit: `git add .env.example docs/dev/2026-10-29-auth-header-plan.md` / `git commit -m "Add BE-15 plan and TEST_DATABASE_URL example"`

### Task 1: Test DB fixtures

**Files:**
- Modify: `tests/conftest.py`
- Test: `tests/test_db_fixtures.py`

**Interfaces:**
- Produces (pytest fixtures, available to every test):
  - `db() -> Session` — session on the test DB inside an outer transaction that is rolled back after the test; `commit()` in app code only releases a savepoint. Skips if `TEST_DATABASE_URL` is unset; fails if the DB name does not end in `_test`.
  - `client(db) -> TestClient` — `app` with `get_db` overridden to yield `db`; override removed after the test.
  - `make_user(username: str) -> int` (inserts `password_hash='x'`), `make_field(user_id: int) -> int`, `make_zone(field_id: int, user_id: int) -> int`. Fixtures that return these callables; each returns the new row id. Field/zone use geometry `ST_GeomFromText('MULTIPOLYGON(((0 0,10 0,10 10,0 10,0 0)))', 5179)`; the zone uses the lowest `crop.id`, name `'z'` / field name `'f'`.

- [ ] **Step 1: Write the failing tests** in `tests/test_db_fixtures.py`
```python
from sqlalchemy import text

PROBE = "rollback-probe"

def _count(db):
    return db.scalar(text("SELECT count(*) FROM users WHERE username = :n"), {"n": PROBE})

def test_a_inserts_probe_user(db, make_user):
    make_user(PROBE)
    assert _count(db) == 1

def test_b_probe_user_was_rolled_back(db):   # relies on definition order: runs after test_a
    assert _count(db) == 0

def test_zone_is_linked_to_its_field_and_user(db, make_user, make_field, make_zone):
    uid = make_user("farmer")
    fid = make_field(uid)
    zid = make_zone(fid, uid)
    row = db.execute(text("SELECT field_id, user_id FROM zone WHERE id = :i"), {"i": zid}).one()
    assert tuple(row) == (fid, uid)
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_db_fixtures.py -v` — Expected: ERROR `fixture 'db' not found`.
- [ ] **Step 3: Implement the fixtures in `tests/conftest.py`.** Top of file, before any `app` import: `TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or dotenv_values(<repo root>/".env").get("TEST_DATABASE_URL")`; `os.environ["DATABASE_URL"] = TEST_DATABASE_URL or "<existing dummy url>"` (assignment, not `setdefault`); keep the existing `setdefault`s for the other two variables and update the comment. Then the fixtures. The `db` body is the standard SQLAlchemy 2 recipe:
```python
@pytest.fixture
def db():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set")
    from app.core.db import engine
    assert engine.url.database.endswith("_test"), "refusing to run on a non-test database"
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()
```
`app` imports go inside the fixtures (or after the env block) so `Settings()` sees the forced URL.
- [ ] **Step 4: Run** the same command — Expected: `3 passed`. Then `.venv\Scripts\python -m pytest -q` — Expected: all existing tests still pass.
- [ ] **Step 5: Commit** `git add tests/conftest.py tests/test_db_fixtures.py` / `git commit -m "Add rollback-per-test DB fixtures"`

### Task 2: `current_user`

**Files:**
- Create: `app/core/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `get_db` (`app/core/db.py`), `AppError` (`app/core/errors.py`), fixtures from Task 1.
- Produces: `current_user(x_user_id: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)) -> int` — the authenticated user's id. Task 3's owned-checks depend on it.

- [ ] **Step 1: Write the failing tests** in `tests/test_auth.py`
```python
from typing import Annotated

import pytest
from fastapi import Depends
from sqlalchemy import text

from app.core.auth import current_user
from app.main import app

UNAUTHORIZED = {"error": {"code": "UNAUTHORIZED", "message": "인증이 필요합니다"}}


@app.get("/_test/me")
def _me(user_id: Annotated[int, Depends(current_user)]):
    return {"user_id": user_id}


def test_valid_header_returns_the_user_id(client, make_user):
    uid = make_user("farmer")
    r = client.get("/_test/me", headers={"X-User-Id": str(uid)})
    assert (r.status_code, r.json()) == (200, {"user_id": uid})


def test_missing_header_is_401(client):
    r = client.get("/_test/me")
    assert (r.status_code, r.json()) == (401, UNAUTHORIZED)


@pytest.mark.parametrize(
    "value", ["", "abc", "0", "-1", "+1", "01", "1.5", "1_0", "1,2", "9" * 19, "١٢".encode()]
)
def test_malformed_header_is_401(client, value):
    r = client.get("/_test/me", headers={"X-User-Id": value})
    assert (r.status_code, r.json()) == (401, UNAUTHORIZED)


def test_withdrawn_or_unknown_user_is_401(client, db, make_user):
    uid = make_user("gone")
    db.execute(text("DELETE FROM users WHERE id = :i"), {"i": uid})
    for value in (str(uid), "9" * 18):
        r = client.get("/_test/me", headers={"X-User-Id": value})
        assert (r.status_code, r.json()) == (401, UNAUTHORIZED)


def test_error_does_not_echo_the_header_value(client):
    r = client.get("/_test/me", headers={"X-User-Id": "secret-value"})
    assert "secret-value" not in r.text
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_auth.py -v` — Expected: collection ERROR `No module named 'app.core.auth'`.
- [ ] **Step 3: Implement `current_user` in `app/core/auth.py`.** Module constant `_USER_ID = re.compile(r"[1-9][0-9]{0,17}")` (`[0-9]`, not `\d`, on purpose); header missing or `fullmatch` fails → `AppError("UNAUTHORIZED", 401, "인증이 필요합니다")`; else `db.scalar(text("SELECT id FROM users WHERE id = :id"), {"id": int(x_user_id)})` is `None` → same error. Return the id.
- [ ] **Step 4: Run** the same command — Expected: all pass. (If the client rejects the `bytes` header value, send it via `headers=[(b"x-user-id", value)]`.)
- [ ] **Step 5: Commit** `git add app/core/auth.py tests/test_auth.py` / `git commit -m "Add X-User-Id current_user dependency"`

### Task 3: `get_owned_field`, `get_owned_zone`

**Files:**
- Modify: `app/core/auth.py`, `tests/test_auth.py`, `docs/dev/팜가디언_아키텍처.md` (§9 인증 bullet, 테스트 bullet)

**Interfaces:**
- Consumes: `current_user` (Task 2), `get_db`, `AppError`.
- Produces: `get_owned_field(field_id: int, user_id: Annotated[int, Depends(current_user)], db: Session = Depends(get_db)) -> int` and `get_owned_zone(zone_id: int, ...) -> int` (same shape). Both return the id; not found or not owned → `AppError("NOT_FOUND", 404, "찾을 수 없습니다")`. Usage: `dependencies=[Depends(get_owned_field)]` or `zone_id: Annotated[int, Depends(get_owned_zone)]`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_auth.py`; add `get_owned_field, get_owned_zone` to the import)
```python
NOT_FOUND = {"error": {"code": "NOT_FOUND", "message": "찾을 수 없습니다"}}


@app.get("/_test/fields/{field_id}", dependencies=[Depends(get_owned_field)])
def _field(field_id: int):
    return {"field_id": field_id}


@app.get("/_test/zones/{zone_id}")
def _zone(zone_id: Annotated[int, Depends(get_owned_zone)]):
    return {"zone_id": zone_id}


def _as(uid):
    return {"X-User-Id": str(uid)}


def test_owner_reads_own_field_and_zone(client, make_user, make_field, make_zone):
    uid = make_user("owner")
    fid = make_field(uid)
    zid = make_zone(fid, uid)
    assert client.get(f"/_test/fields/{fid}", headers=_as(uid)).json() == {"field_id": fid}
    assert client.get(f"/_test/zones/{zid}", headers=_as(uid)).json() == {"zone_id": zid}


def test_other_users_resources_look_like_missing_ones(client, make_user, make_field, make_zone):
    owner, other = make_user("owner"), make_user("other")
    fid = make_field(owner)
    zid = make_zone(fid, owner)
    for path in (f"/_test/fields/{fid}", f"/_test/zones/{zid}"):
        r = client.get(path, headers=_as(other))
        assert (r.status_code, r.json()) == (404, NOT_FOUND)
    missing = client.get("/_test/fields/123456789", headers=_as(other))
    assert missing.json() == NOT_FOUND


def test_missing_header_beats_not_found(client):
    r = client.get("/_test/fields/123456789")
    assert (r.status_code, r.json()) == (401, UNAUTHORIZED)


@pytest.mark.parametrize("rid", [0, -1, 10**20])
def test_out_of_range_ids_are_404(client, make_user, rid):
    uid = make_user("owner")
    for path in (f"/_test/fields/{rid}", f"/_test/zones/{rid}"):
        r = client.get(path, headers=_as(uid))
        assert (r.status_code, r.json()) == (404, NOT_FOUND)


def test_non_integer_id_is_validation_error(client, make_user):
    r = client.get("/_test/fields/abc", headers=_as(make_user("owner")))
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_auth.py -v` — Expected: collection ERROR `cannot import name 'get_owned_field'`.
- [ ] **Step 3: Implement both in `app/core/auth.py`.** Query: `SELECT 1 FROM field WHERE id = :id AND user_id = :uid` (zone: same on `zone`) — one query, no join. Keep the two SQL strings as fixed `text()` constants; share the "raise NOT_FOUND if no row" logic in one small private helper.
- [ ] **Step 4: Run** the same command — Expected: all pass.
- [ ] **Step 5: Docs.** In `docs/dev/팜가디언_아키텍처.md` §9: append to the 인증 bullet "경로 매개변수 이름은 `field_id`·`zone_id`로 통일한다 (의존성이 경로에서 직접 읽는다). 남의 것이거나 없으면 404." and to the API 테스트 bullet "`TEST_DATABASE_URL`(이름이 `_test`로 끝나는 DB)이 없으면 DB 테스트는 skip된다."
- [ ] **Step 6: Commit** `git add app/core/auth.py tests/test_auth.py docs/dev/팜가디언_아키텍처.md` / `git commit -m "Add get_owned_field and get_owned_zone dependencies"`

### Task 4: `dev` user seed

**Files:**
- Create: `app/seed_demo.py`
- Test: `tests/test_seed_demo.py`

**Interfaces:**
- Consumes: `SessionLocal` (`app/core/db.py`), fixtures from Task 1.
- Produces: `ensure_dev_user(db: Session) -> int` (inserts `users('dev', '!')` if absent, returns its id, never commits); `main(argv: list[str] | None = None) -> None` (argparse, `--dev-user` required for now; opens a session, calls `ensure_dev_user`, commits, prints `dev user id: <n>`); `python -m app.seed_demo --dev-user` runs `main()`.

- [ ] **Step 1: Write the failing tests** in `tests/test_seed_demo.py`
```python
from sqlalchemy import text

from app.seed_demo import ensure_dev_user


def test_creates_the_locked_dev_user(db):
    uid = ensure_dev_user(db)
    row = db.execute(text("SELECT username, password_hash FROM users WHERE id = :i"), {"i": uid}).one()
    assert tuple(row) == ("dev", "!")


def test_is_idempotent(db):
    first, second = ensure_dev_user(db), ensure_dev_user(db)
    assert first == second
    assert db.scalar(text("SELECT count(*) FROM users WHERE username = 'dev'")) == 1
```
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests\test_seed_demo.py -v` — Expected: collection ERROR `No module named 'app.seed_demo'`.
- [ ] **Step 3: Implement** with `INSERT … ON CONFLICT (username) DO NOTHING` then `SELECT id … WHERE username = 'dev'`. Put a short comment on the `'!'` hash (locked: header-only user; BE-17 login must not match it). `python -m app.seed_demo` without `--dev-user` must exit non-zero with argparse's usage error.
- [ ] **Step 4: Run** the same command — Expected: `2 passed`.
- [ ] **Step 5: Commit** `git add app/seed_demo.py tests/test_seed_demo.py` / `git commit -m "Add dev user seed"`

### Task 5: Final verification

- [ ] **Step 1:** `.venv\Scripts\python -m pytest -q` — Expected: all pass, no skips (TEST_DATABASE_URL is set).
- [ ] **Step 2:** `.venv\Scripts\ruff check .` — Expected: `All checks passed!`
- [ ] **Step 3:** Fresh-clone check: rename `.env` to `.env.off` (rename, never delete), run `.venv\Scripts\python -m pytest -q -rs` — Expected: DB tests reported as skipped with `TEST_DATABASE_URL not set`, all others pass; rename `.env.off` back to `.env` and confirm it exists.
- [ ] **Step 4:** Run the seed against the dev DB: `.venv\Scripts\python -m app.seed_demo --dev-user` twice — Expected: the same `dev user id: <n>` both times; tell the user the id (the frontend uses it as the fixed `X-User-Id`). This writes one row to the dev DB.
- [ ] **Step 5:** `git status -sb` — Expected: clean. Do not push; tell the user the branch is ready for a PR to `test` after `feat/jh-db-setup`.
