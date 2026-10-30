# Login, My Info, Onboarding, Withdrawal (BE-17 login part, BE-18, BE-19) Design

Date: 2026-10-29. Frame: `docs/dev/팜가디언_API_명세.md` §3 (never edited; this design conforms to it).
Decided before: `팜가디언_아키텍처.md` (session = `X-User-Id`, passwords with `hashlib.scrypt`, onboarding =
`users.onboarded_at`, "demo-grade security").

## Goal

The `identity` context with four endpoints that need nothing from teammates' unfinished work:

- `POST /auth/login` — username and password → `{id, username}` (no auth header)
- `GET /me` — `{id, username, onboarded}`
- `POST /me/onboarding` — record that first-use onboarding is finished (idempotent)
- `DELETE /me` — withdraw: the user and everything that belongs to them

Plus the identity half of signup as a tested building block (`register_user`), so signup is a small
step once the farm side exists.

## Non-goals

- **The `POST /auth/signup` route.** It creates a user and the first field in one transaction through
  `farm.application.field_service` (spec §3), and that function did not exist yet when this was
  written. It became a follow-up, designed in "Signup" at the end of this document.
- Tokens, sessions, brute-force limits, password reset: the architecture says security stays minimal
  for the demo.

## Layout

```
app/identity/
  domain/password.py            hash_password / verify_password — pure, hashlib.scrypt
  infrastructure/repository.py  SQL on users (sqlalchemy text(), like core/auth.py)
  application/service.py        register_user, login, get_me, complete_onboarding, withdraw
  presentation/router.py, schemas.py
```

Small change in the farm folder (it is 혜빈님's, so it needs her review; same pattern as the
judgment's `zone_reader`): `farm/application/zone_reader.py` gets
`list_user_zones(db, user_id) -> list[ZoneState(id, history_confirmed)]` (all zones of the user, by
id), because onboarding asks about zones and `identity` must not read another context's table.
`app/main.py` registers the router.

## Behavior

### Password (domain, pure)

`hash_password(password: str, salt: bytes | None = None) -> str` and
`verify_password(password: str, stored: str) -> bool`.

- Format `scrypt$<n>$<r>$<p>$<salt hex>$<hash hex>` with n = 2^14, r = 8, p = 1 (about 16 MiB, tens of
  ms), a random 16-byte salt, 32-byte hash. The parameters are stored in the string, so they can be
  raised later and old hashes still verify.
- The password is UTF-8 encoded; comparison is `hmac.compare_digest`.
- `verify_password` never raises: a stored value that is not in this format (the dev user's `!`, the
  `x` of test fixtures, an empty string, truncated or non-hex parts, absurd parameters) is a
  mismatch.

### `register_user(db, username, password) -> int | None`

`INSERT ... ON CONFLICT (username) DO NOTHING RETURNING id` with the hashed password; `None` when the
name is taken (the caller turns it into 409 `USERNAME_TAKEN`). It does not commit, so a later signup can
roll the user back when the field creation fails (spec: 502 leaves no user). Usernames are compared
exactly as the column does (case-sensitive).

### `POST /auth/login`

- Body `{username, password}`, both strings 1..100 characters (a longer value is a 422 shape error;
  no account can have it, and it bounds the work). Anything else wrong is **401 `UNAUTHORIZED`** with one
  message: unknown name, wrong password, locked hash all look the same (spec).
- An unknown name still runs one `verify_password` against a fixed dummy hash, so the response time
  does not tell whether the name exists.
- 200 `{id, username}`. No `X-User-Id` is needed (and one that is sent is ignored).

### `GET /me`

Behind `current_user`. 200 `{id, username, onboarded}`, `onboarded` = `onboarded_at IS NOT NULL`.

### `POST /me/onboarding`

Behind `current_user`, no body.

1. Already onboarded → **200 `{id, onboarded: true}`** at once. It is not re-checked and the first
   completion time is kept: the "no omission" confirmation of a zone is reset when its planting date
   changes, so it cannot be used to undo a finished onboarding (architecture decision).
2. Otherwise the user's zones are read through `farm`: no zone, or any zone with
   `history_confirmed` false → **422 `ONBOARDING_INCOMPLETE`**, `details` =
   `{zone_count: int, unconfirmed_zone_ids: [int]}` (ids ascending).
3. Otherwise `UPDATE users SET onboarded_at = now() WHERE id = :id AND onboarded_at IS NULL`, commit,
   200 `{id, onboarded: true}`.

### `DELETE /me`

Behind `current_user`. `DELETE FROM users WHERE id = :id` and commit; the foreign keys cascade to
fields, parcels, zones, spray records and judgments (schema). 204 with no body. Afterwards the same
`X-User-Id` gets 401 (`current_user` reads `users`), including a second `DELETE /me`.

## Decisions I made where the spec is silent

1. Login length bound 1..100 (422 beyond), and timing equalization with a dummy hash.
2. scrypt parameters and the stored format above.
3. Once onboarded, `POST /me/onboarding` stays 200 and keeps the first timestamp.
4. `unconfirmed_zone_ids` is sorted ascending; `zone_count` counts all zones.
5. Usernames are case-sensitive, like the column.
6. The `dev` user (hash `!`) can never log in and can be withdrawn like anyone else.
7. `register_user` does not commit; the caller owns the transaction.

## Tests

DB-backed through the existing fixtures; users are created with `register_user`, so the login tests use
real hashes.

- **Password:** round trip (ASCII and Korean), different salts give different hashes, wrong password,
  the stored string carries its parameters and a hash made with other parameters still verifies,
  every malformed or locked stored value (`!`, `x`, empty, wrong part count, non-hex, huge `n`) is
  `False` without an exception.
- **Service:** `register_user` stores a verifiable hash and returns the id, a second call with the
  same name returns `None` and stores nothing; `login` for each failure mode returns the same result.
- **Login API:** 200 shape, wrong password / unknown user / dev user / empty-hash user all the same 401
  body, no header needed, over-long and missing fields 422, the dummy verification is used for an
  unknown name (the verify function is called once).
- **`/me`:** 401 without a header, shape, `onboarded` false then true.
- **Onboarding:** no zone → 422 with `{0, []}`; one confirmed and one unconfirmed zone → 422 listing
  the unconfirmed id; all confirmed → 200 and `/me` says onboarded; a second call is 200 and the time
  does not change; after completion an unconfirmed zone still gives 200; another user's zones do not
  count.
- **Withdrawal:** 204 and an empty body; the user, fields, parcels, zones, spray records and judgments
  are gone and another user's rows are not touched; the same header is then 401 on `GET /me` and on a
  second `DELETE /me`.

## Known limits

- Anyone who knows a user id can call `/me*` (architecture: `X-User-Id` is not a secret).
- No limit on login attempts.
- Withdrawal is irreversible and has no confirmation step (the frontend asks).

## Signup (added 2026-10-30)

`field_service.create_field(db, user_id, name, farmmap_ids) -> dict` now exists (PR #22) with the
contract asked for above: it runs in the caller's transaction, never commits, and raises `AppError`
for 409 `PARCEL_ALREADY_USED`, 422 (`loc` `["body","parcel_farmmap_ids",i]`, `type` `not_found`) and
502 `UPSTREAM_ERROR`. Approved in chat 2026-10-30; frame = API spec §3 `POST /auth/signup`.

### `POST /auth/signup` (no auth)

- Body `SignupIn`: `username` `^[A-Za-z0-9_]{3,30}$`; `password` 4..72 characters, untouched;
  `field_name` 1..30 characters after stripping outer whitespace (same as `POST /fields`, my call);
  `parcel_farmmap_ids` 1..20 distinct ASCII-digit strings, built from farm's `FarmmapId` and
  `check_unique` so the rule lives in one place (my call; farm's file is not touched).
- `service.signup(db, username, password, field_name, farmmap_ids) -> dict`: `register_user` (`None`
  → 409 `USERNAME_TAKEN`, before any Farmmap call) → `create_field` → `db.commit()` → 201
  `{id, username, field}`. `field` is farm's `FieldOut` (`zones: []`).
- Any exception from `create_field` rolls the session back explicitly before it propagates, so the
  new user disappears with it (spec: a 502 leaves no user). `get_db` would also roll back on close,
  but the test client reuses one session, so the service does not rely on that (my call).
- The user row is inserted before the Farmmap calls (spec order), so a concurrent signup with the same
  name waits on the unique index until this one ends. Fine at demo scale.
- Not done: login attempt limits, tokens or sessions (`X-User-Id` stays).
