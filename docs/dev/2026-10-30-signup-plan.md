# Signup Implementation Plan (BE-17 signup part)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (project CLAUDE.md: no subagent-driven execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /auth/signup` in the shape of API spec §3: create the user and the first field in one transaction.

**Architecture:** `identity` gets one route, one body/response model pair and one service function. The service calls `register_user` (exists) and then `farm.application.field_service.create_field` (PR #22), commits once on success and rolls the session back if `create_field` fails. No farm file is touched.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2, pytest against the PostGIS test database with the fake Farmmap from `tests/farm_support.py`.

**Spec:** `docs/dev/2026-10-29-auth-design.md`, section "Signup (added 2026-10-30)" (approved in chat 2026-10-30); frame = `docs/dev/팜가디언_API_명세.md` §3 `POST /auth/signup` (never edited).

## Global Constraints

- `팜가디언_API_명세.md`, `schema.sql`, `requirements*.txt` and everything under `app/farm/` do not change.
- Request body: `username` `^[A-Za-z0-9_]{3,30}$`; `password` 4..72 characters, not stripped; `field_name` 1..30 characters after stripping outer whitespace; `parcel_farmmap_ids` 1..20 distinct strings of ASCII digits (farm's `FarmmapId` and `check_unique`).
- Response 201 `{id: int, username: str, field: FieldOut}` with `field.zones == []`. No auth header needed (`/auth/signup` has no auth dependency).
- Errors in the common format: 409 `USERNAME_TAKEN` (message `이미 사용 중인 아이디입니다`, my call; raised before any Farmmap call); 422 `VALIDATION_ERROR` for body errors and for an unknown id (`details.errors[].loc` `["body","parcel_farmmap_ids",i]`, `type` `not_found`, both come from `create_field`); 502 `UPSTREAM_ERROR` with `details` `{"source": "farmmap"}`. After any of them no user row exists.
- Transaction: `register_user` and `create_field` never commit; `signup` commits exactly once, after both succeeded. Any exception from `create_field` triggers `db.rollback()` before it propagates (the test client reuses one session, so closing the session cannot be relied on).
- Usernames are case-sensitive (design decision 5). `X-User-Id` is ignored.
- `identity.application` reaches farm only through `farm.application.field_service`; `identity.presentation.schemas` imports `FarmmapId`, `check_unique`, `FieldOut` from `farm.presentation.schemas` (same pattern as farm and spraying importing catalog's schemas).
- Code and identifiers in English, short Korean comments like `app/identity`; ruff line length 100 (Korean counts double); tests flat in `tests/`; commit messages in English with the session's attribution trailer; do not push; stage explicit paths only (the working tree has an unrelated uncommitted backlog xlsx and `.gitignore` change).

## Review Focus

- A failed signup (missing parcel 422, Farmmap 502) leaves no user and the same username can sign up again right after. (Task 2)
- A taken username gives 409 without any Farmmap call and leaves the existing account (password included) untouched. (Task 2)
- Bodies that look valid but are not give 422 and no user row: username with a trailing newline, spaces, non-ASCII or full-width digits; 3-character and 73-character passwords; whitespace-only field name; 0, 21 or duplicate ids. (Tasks 1, 2)
- A correct signup is usable at once: logging in with the password works and the new id sees exactly the created field in `GET /fields`. (Task 2)
- `Farmer_1` and `farmer_1` are two accounts. (Task 2)

---

### Task 0: Branch and commit the design and this plan

- [ ] **Step 1:** `git switch -c feat/jh-signup` (from `test` at `f4f3b26`; the unrelated uncommitted files stay uncommitted).
- [ ] **Step 2:** `git add docs/dev/2026-10-29-auth-design.md docs/dev/2026-10-30-signup-plan.md` / `git commit -m "Add signup design and plan"`.

### Task 1: Body and response models

**Files:**
- Modify: `app/identity/presentation/schemas.py`
- Create: `tests/test_identity_signup.py`

**Interfaces:**
- Consumes: `FarmmapId`, `check_unique`, `FieldOut` from `app.farm.presentation.schemas`.
- Produces: `SignupIn(username: str, password: str, field_name: str, parcel_farmmap_ids: list[str])` and `SignupOut(id: int, username: str, field: FieldOut)`, both Pydantic models in `app/identity/presentation/schemas.py`.

- [ ] **Step 1: Write the failing tests** in `tests/test_identity_signup.py` (this task adds only the model tests; imports `SignupIn` and `pydantic.ValidationError`):

```python
VALID = {
    "username": "farmer_1",
    "password": "pw1234",
    "field_name": "앞밭",
    "parcel_farmmap_ids": ["1", "2"],
}


def body(**changes):
    return {**VALID, **changes}


def test_valid_body_is_accepted_and_the_field_name_is_stripped():
    parsed = SignupIn.model_validate(body(field_name="  앞밭  "))
    assert (parsed.username, parsed.password, parsed.field_name) == ("farmer_1", "pw1234", "앞밭")
    assert parsed.parcel_farmmap_ids == ["1", "2"]


def test_boundary_values_are_accepted():
    SignupIn.model_validate(body(username="abc", password=" " * 4, field_name="f"))  # no strip
    SignupIn.model_validate(
        body(username="a" * 30, password="x" * 72, field_name="f" * 30,
             parcel_farmmap_ids=[str(i) for i in range(1, 21)])
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"username": "ab"}, {"username": "a" * 31}, {"username": "farmer\n"},
        {"username": "farm er"}, {"username": "farmer-1"}, {"username": "농부농부"},
        {"username": "１２３４"},
        {"password": "abc"}, {"password": "x" * 73},
        {"field_name": ""}, {"field_name": "   "}, {"field_name": "f" * 31},
        {"parcel_farmmap_ids": []}, {"parcel_farmmap_ids": [str(i) for i in range(1, 22)]},
        {"parcel_farmmap_ids": ["1", "1"]}, {"parcel_farmmap_ids": [""]},
        {"parcel_farmmap_ids": ["12a"]}, {"parcel_farmmap_ids": ["１２"]},
    ],
)
def test_invalid_bodies_are_rejected(changes):
    with pytest.raises(ValidationError):
        SignupIn.model_validate(body(**changes))


@pytest.mark.parametrize("missing", list(VALID))
def test_a_missing_key_is_rejected(missing):
    with pytest.raises(ValidationError):
        SignupIn.model_validate({k: v for k, v in VALID.items() if k != missing})
```

- [ ] **Step 2:** `pytest tests/test_identity_signup.py -v` → FAIL (`ImportError: cannot import name 'SignupIn'`).
- [ ] **Step 3:** Add `SignupIn` and `SignupOut` to `app/identity/presentation/schemas.py` with the constraints in Global Constraints (`field_name` and `parcel_farmmap_ids` annotated like farm's `FieldCreate`, reusing its building blocks instead of copying their rules).
- [ ] **Step 4:** `pytest tests/test_identity_signup.py -v` → all PASS.
- [ ] **Step 5:** `git add app/identity/presentation/schemas.py tests/test_identity_signup.py` / `git commit -m "Add signup request and response models"`.

### Task 2: Service and route

**Files:**
- Modify: `app/identity/application/service.py`, `app/identity/presentation/router.py`
- Modify: `tests/test_identity_signup.py`

**Interfaces:**
- Consumes: Task 1's `SignupIn`, `SignupOut`; `register_user(db, username, password) -> int | None`; `field_service.create_field(db, user_id: int, name: str, farmmap_ids: list[str]) -> dict`; `service.login(db, username, password) -> tuple[int, str] | None`.
- Produces: `signup(db: Session, username: str, password: str, field_name: str, farmmap_ids: list[str]) -> dict` in `app/identity/application/service.py` returning `{"id", "username", "field"}`; route `POST /auth/signup` (201, `response_model=SignupOut`).

- [ ] **Step 1: Write the failing tests**: extend `tests/test_identity_signup.py` with the imports `text`, `service`, `install_fake_farmmap`, a local `fake_farmmap` fixture (`return install_fake_farmmap(monkeypatch)`, same as `tests/test_fields_api.py`; its tuple is `(calls, missing, failing)`) and these helpers/tests (`signup(client, **changes)` posts `body(**changes)` to `/auth/signup` without headers; `total_users(db)` is `SELECT count(*) FROM users`):

  - `test_signup_creates_the_user_and_the_first_field`: 201; keys exactly `{id, username, field}`; `field` keys `{id, name, area_m2, geometry, bbox, zones}`, `name == "앞밭"`, `area_m2 == 200.0`, `zones == []`; `GET /fields` with `X-User-Id` = the new id returns `[data["field"]]`; `POST /auth/login` with the password returns 200 `{id, username}` of the new user.
  - `test_taken_username_is_409_before_any_farmmap_call`: first `service.register_user(db, "farmer_1", "other_pw")`; signup → 409, code `USERNAME_TAKEN`; farmmap `calls == []`; `total_users` is unchanged; `service.login(db, "farmer_1", "other_pw")` still returns the old user.
  - `test_usernames_are_case_sensitive`: signups for `Farmer_1` and `farmer_1` both 201.
  - `test_unknown_parcel_is_422_and_leaves_no_user`: `missing.add("2")`; 422, `VALIDATION_ERROR`, `details.errors` is one item with `loc == ["body", "parcel_farmmap_ids", 1]` and `type == "not_found"`; `total_users` unchanged.
  - `test_farmmap_failure_is_502_leaves_no_user_and_the_name_is_free_again`: `failing.add("1")`; 502, `details == {"source": "farmmap"}`, `total_users` unchanged; `failing.clear()`; the same signup is now 201.
  - `test_invalid_body_is_422_before_any_user_or_farmmap_call` (parametrized over `{"parcel_farmmap_ids": ["1", "1"]}`, `{"username": "ab"}`, `{"password": "abc"}`, `{"field_name": " "}`): 422, code `VALIDATION_ERROR`, `calls == []`, `total_users` unchanged.

- [ ] **Step 2:** `pytest tests/test_identity_signup.py -v` → the six new tests FAIL (404 on `/auth/signup`).
- [ ] **Step 3: Implement `signup(...)` in `app/identity/application/service.py`:** `register_user`; `None` → `AppError("USERNAME_TAKEN", 409, "이미 사용 중인 아이디입니다")`; then `field_service.create_field` inside `try`/`except Exception: db.rollback(); raise` (comment: the new user goes with it); `db.commit()`; return the dict. Import `field_service` from `app.farm.application`.
- [ ] **Step 4: Add the route** in `app/identity/presentation/router.py`: `@router.post("/auth/signup", response_model=SignupOut, status_code=201)` with `body: SignupIn` and `db: Session = Depends(get_db)`, no auth dependency, calling `service.signup(db, body.username, body.password, body.field_name, body.parcel_farmmap_ids)`.
- [ ] **Step 5:** `pytest tests/test_identity_signup.py -v` → all PASS.
- [ ] **Step 6:** `git add app/identity/application/service.py app/identity/presentation/router.py tests/test_identity_signup.py` / `git commit -m "Add POST /auth/signup"`.

### Task 3: Verify the whole suite

- [ ] **Step 1:** `pytest -q -rs` → every test passes and none is skipped (a skipped DB test means `TEST_DATABASE_URL` is not read; fix that before going on).
- [ ] **Step 2:** `ruff check .` → `All checks passed!`.
- [ ] **Step 3:** `git status -sb` shows only the two unrelated uncommitted files (`.gitignore`, the backlog xlsx) and the branch `feat/jh-signup` is 3 commits ahead of `origin/test`.
- [ ] **Step 4:** Report to the user: the commands run and their output, the explicit-rollback call (deviation from "no extra code", reason: the test client reuses one session), and that push and PR wait for their word. After the merge, still open: Notion row for signup, backlog BE-17 check (xlsx via the XML-edit method in the project notes, only if Excel is closed), `Field.address` question untouched.
