# Fields: create, list, delete (design)

- Date: 2026-10-29
- Owner: Hyebin (farm context), issue #4
- Status: approved in chat (2026-10-30); updated for PRs #15–#21 (spraying, judgment, identity)
- Basis: `팜가디언_API_명세.md` §1, §2 (`Field`, `ZoneSummary`, `Parcel`), §3 `POST /auth/signup`, §5;
  `팜가디언_아키텍처.md` §5 (tables), §7 「밭 생성」; `schema.sql` (`field`, `field_parcel`, `zone`, `crop`);
  `app/core/auth.py` (PR #11)

## Intent

A user registers a field by picking Farmmap parcels on the map. A field is the union of those parcels
and is later split into zones (#5). This adds field create / list / delete, and marks parcels that
the user's other fields already use in `GET /parcels`, so the map can grey them out.

## Goals

1. `POST /fields` — body `{name, parcel_farmmap_ids}` → 201 `Field` with `zones: []`.
2. `GET /fields` — 200 `[Field]` of the current user, in creation order (`field.id`), each with
   `zones: [ZoneSummary]` ordered by `zone.id`.
3. `DELETE /fields/{id}` — 204; zones, spray logs, judgments go with it (`ON DELETE CASCADE` in
   `schema.sql`, no extra code). Not mine or not found → 404 via `get_owned_field`.
4. `GET /parcels` — when an `X-User-Id` header is sent, fill `used_by_field_id` with the id of the
   user's field that holds that `farmmap_id`. Without the header it stays `null` (still no auth
   required).
5. A field-creation function the signup endpoint (Junhyeok, `POST /auth/signup`) can call inside its
   own transaction.

## Non-goals

- `last_judgment` in `ZoneSummary` is always `null` in this work. The judgment context (PR #20) only
  writes judgments; it has no read function, and the farm context may only call other contexts'
  `application` services (arch §4). Filling it needs a small read function in
  `judgment.application.service` (Junhyeok's folder) — a follow-up to ask him for.
  (Originally both `last_spray` and `last_judgment` were to be `null`, agreed with Hyebin; spraying
  landed in PR #19 since then, so `last_spray` is filled — see below.)
- Splitting and zones (#5, #6), signup itself, renaming a field (not in the spec).

## Behaviour

### `POST /fields`

Request validation (422 `VALIDATION_ERROR`, before any DB or Farmmap call):
- `name`: 1–30 chars.
- `parcel_farmmap_ids`: 1–20 items, no duplicates, each a string of ASCII digits (builder's call on the
  exact max length; live ids are 15 digits). Empty or non-numeric ids must be rejected here, because
  Farmmap answers an empty id with code 11, which would surface as 502 (see
  `2026-10-29-parcel-by-id-design.md`).

Then, in this order:
1. **Already used** — if any requested id is in `field_parcel` for this user → 409
   `PARCEL_ALREADY_USED`, `details: {farmmap_ids: [...]}` (the used ones, in request order). Checked
   in the DB before calling Farmmap so no external calls are wasted (builder's call, agreed in chat).
2. **Fetch** every parcel with `farmmap.parcel_by_id`, in parallel, at most 8 at a time (arch §7).
   - Any Farmmap failure → 502 `UPSTREAM_ERROR` `source: "farmmap"` (raised by the client). Nothing
     is saved.
   - Ids that come back `None` → 422 `VALIDATION_ERROR` with one error per missing id:
     `{loc: ["body", "parcel_farmmap_ids", <index>], msg, type: "not_found"}` (API spec §3). Report
     all missing ids, not just the first (my call).
3. **Save** in one transaction: insert `field` (geometry = union of the parcel geometries, always a
   MultiPolygon), then one `field_parcel` row per parcel with `farmmap_id, pnu, lnm, land_use,
   vdpt_yr, geom`. Parcels that are far apart still form one field (MultiPolygon).
4. If two requests race and the `UNIQUE (user_id, farmmap_id)` constraint fires on insert, answer
   409 `PARCEL_ALREADY_USED` too, not 500. The inserts run in a savepoint (`db.begin_nested()`), so
   only they roll back and a caller's outer transaction (signup's user insert) stays usable; the
   used ids are then re-read for `details.farmmap_ids` (my call).

### `Field` shape

`{id, name, area_m2, geometry, bbox, zones}` per API spec §1–2: `area_m2` = area of `field.geom` in ㎡
(rounded to 1 decimal like `GET /parcels`), `geometry` = GeoJSON MultiPolygon in EPSG:5179 with 1
decimal and only `type` + `coordinates` (no `crs` member, same shape as `Parcel.geometry`),
`bbox = [minx, miny, maxx, maxy]`.

`ZoneSummary` = `{id, name, crop: {id, name}, planted_at, history_confirmed, area_m2, geometry,
last_spray, last_judgment: null}`. `crop` comes from the `crop` table (seeded with 3 crops by
`schema.sql`).

`last_spray` = the zone's most recent spray as `Spray` (`{id, pesticide, sprayed_on, source}`, the
same shape as `GET /zones/{id}/sprays` items), or `null`. Taken from
`spraying.application.spray_service.list_sprays(db, zone_id, limit=1)` (newest first) and shaped
with `catalog.presentation.schemas.pesticide_base`, as the spraying router does. One call per zone is
fine at demo scale (a few zones per user).

Zone summaries are built by `farm/application/zone_service.summaries(db, field_ids)` (name fixed by
arch §4; `zone_service` is Hyebin's and will also hold #5/#6 zone code).

### `GET /parcels` with a header

- No header → as today, `used_by_field_id: null`, no DB access needed.
- Header present → same rules as `current_user` (bad or unknown id → 401; a separate optional-header
  dependency in the farm context reuses them), then look up this user's
  `field_parcel` rows for the returned `farmmap_id`s. My call: a header that is sent but wrong is an
  error rather than silently ignored, so the frontend notices a broken header.

## Code shape

- Auth: `current_user` and `get_owned_field` from `app/core/auth.py`. `get_owned_field` takes a
  parameter named `field_id`, so the route path is `/fields/{field_id}` (same URL as the spec).
- SQL: raw `text()` statements with PostGIS functions, like `app/core/auth.py`. No ORM models — that
  would need GeoAlchemy2 for the geometry columns and nothing else uses models yet (my call; the
  "models" checkbox on issue #4 is dropped).
- Layers as today: Farmmap calls in `infrastructure/integrations/farmmap.py` (unchanged), DB access
  in a new `farm/infrastructure` repository module, orchestration in
  `farm/application/field_service.py`, request/response models in `farm/presentation/schemas.py`,
  routes in `farm/presentation/router.py`.
- Signup hook: `field_service.create_field(db, user_id, name, farmmap_ids) -> dict` (the `Field`
  dict). It does not commit; the caller commits (same convention as `seed_demo.ensure_dev_user`).
  `POST /fields` commits after it returns. Signup will validate ids with the same request model rules.
  This matches Junhyeok's `identity.application.service.register_user` (PR #21), which also does
  not commit; his signup route (still missing) calls `register_user` then `create_field` and commits
  once.
- Left to the builder: thread pool details (e.g. `ThreadPoolExecutor(max_workers=8)`, sharing one
  `httpx2.Client`), how geometry is passed to PostGIS (WKT / GeoJSON), using `ST_Union` +
  `ST_Multi`, `ST_Area`, `ST_AsGeoJSON(..., 1)` and `ST_XMin`… for bbox, and whether to wrap
  Farmmap geometry with `ST_MakeValid` if the union fails on real data.

## Tests

DB tests use Junhyeok's fixtures (`db`, `client`, `make_user`, `make_field`, `make_zone`) on
`TEST_DATABASE_URL`; Farmmap is replaced by a fake `parcel_by_id` (no network). Cover:
- create: 201 shape, union area of two adjacent squares, two far-apart parcels → one MultiPolygon,
  rows in `field_parcel`.
- 422: empty list, 21 ids, duplicate ids, empty / non-numeric id, name empty or 31 chars, unknown id
  (`loc` index, `type: "not_found"`, several missing ids).
- 409: id used by my other field (with `details.farmmap_ids`); the same id in another user's field
  is fine.
- 502 from Farmmap → nothing saved.
- 401 without header on all three endpoints.
- list: only my fields, creation order, zone summary with crop, `last_spray` = newest spray (and
  `null` with no sprays), `last_judgment` `null`, empty `zones` for an unsplit field.
- delete: 204, zones gone (CASCADE), someone else's field → 404, unknown id → 404.
- `GET /parcels`: `used_by_field_id` filled with header, `null` without, 401 with a bad header.
