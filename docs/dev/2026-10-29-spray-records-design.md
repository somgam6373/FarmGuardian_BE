# Spray Records (BE-46, BE-47) Design

Date: 2026-10-29. Frame: `docs/dev/팜가디언_API_명세.md` §8 (never edited; this design conforms to it).

## Goal

Three endpoints that store, list and cancel a zone's spray history:

- `POST /zones/{id}/sprays` — save one spray (BE-46: retry-safe, duplicate-aware)
- `GET /zones/{id}/sprays` — paged history (BE-47)
- `DELETE /zones/{id}/sprays/{sid}` — cancel = delete (BE-47)

The history is what the judgment API (BE-45) later reads for checks ③ and ④, so the data model is
exactly the existing `spray_log` table. No schema change.

## Non-goals

- Editing a record (spec: cancel and re-enter).
- `last_spray` for `ZoneSummary` and the judgment input (a list of the zone's records): both belong
  to later tasks (BE-28 by 혜빈님, BE-45). Nothing is pre-built for them; see Coordination.
- Checking that the pesticide is registered for the zone's crop. A history entry records what was
  really sprayed, including off-label use, which is exactly what judgment ③④ must see.

## Layout

New bounded context `app/spraying/`, four layers as in the architecture document:

```
app/spraying/
  domain/entities.py            Spray(id, pesticide_id, sprayed_on, source)           pure
  infrastructure/repository.py  SQL on spray_log (sqlalchemy text(), like core/auth.py)
  application/spray_service.py  record_spray / list_sprays / cancel_spray; commits
  presentation/router.py        three routes, behind current_user + get_owned_zone
  presentation/schemas.py       SprayIn, SprayOut, SprayPage
```

Small changes outside the new folder:

- `catalog_service.get_pesticide(pesticide_id) -> Pesticide | None` (id index over the cached
  `_drugs()`), because a `Spray` carries a full `Pesticide`.
- `catalog/presentation/schemas.py`: `PesticideOut` gets a base class `PesticideBase` without
  `at_planting_only`, plus one converter from the entity, reused by `_pesticide_out` and by the spray
  schemas. `GET /pesticides` output does not change (its tests guard it).
- `app/main.py` registers the router.

`spray_service` is the only caller of `catalog_service` (an application function, allowed across
contexts) and returns `SprayView(spray, pesticide)`, so the router only converts.

## Behavior

All three: 401 without a valid `X-User-Id`; 404 for an unknown zone or another user's zone
(`get_owned_zone`); the ownership 404 wins over body validation, so a foreign zone never reveals
whether the body was valid.

### POST

Body `{pesticide_id: int, sprayed_on?: date, source: "manual"|"app", request_id: uuid,
allow_duplicate?: bool}`. Missing or mistyped fields are 422 through the existing handler; unknown
fields are ignored.

1. Validate (422, `details.errors[0].loc` = `["body", <field>]`, the value is never echoed):
   - `pesticide_id` not in the catalog → `["body","pesticide_id"]`.
   - `sprayed_on` after today (KST) → `["body","sprayed_on"]`; today and the past are valid.
   - `sprayed_on` omitted → today (KST), taken once per request via `today_kst()`.
2. Same `request_id` already stored:
   - in this zone → **200** with that record, nothing is saved again, `allow_duplicate` and the body
     are ignored (a retry must return the original even if the retry differs).
   - in another zone (same or another user) → **422** `["body","request_id"]`, with no record data.
3. Same zone, `pesticide_id` and `sprayed_on` already stored and `allow_duplicate` is not true →
   **409** `DUPLICATE_SPRAY`, `details.existing` = the oldest such record (lowest id) as a `Spray`.
   The 409 stores nothing, so the client may resend the same `request_id` with
   `allow_duplicate: true`. Just before answering 409 the service looks the `request_id` up once
   more: a retry racing its own original would otherwise see the record the original just saved as
   a "duplicate" and get 409 instead of the 200 of step 2.
4. Insert and commit → **201** `Spray`.

Retry safety under concurrency: the insert is `INSERT ... ON CONFLICT (request_id) DO NOTHING
RETURNING ...`. If another request with the same `request_id` wins the race, the insert returns
nothing and the service re-reads by `request_id` and answers as in step 2. The duplicate check of
step 3 is not atomic with the insert; two simultaneous different `request_id`s may both save,
which only costs a duplicate the user can cancel.

### GET

Query `limit` (default 20, 1..100) and `offset` (default 0, >= 0); out of range or non-integer
is 422. Response `{total, items}`: `total` counts the zone's records, `items` are ordered
`sprayed_on` DESC then `id` DESC, one page. An empty history is `{"total": 0, "items": []}`.

### DELETE

Deletes the record only if it belongs to this zone; **204** with no body. A record that does not
exist, was already cancelled, or belongs to another zone (same user or not) is **404**.

### Spray shape

`{id, pesticide: {id, name, item_name, moa: {label_kr, system, code} | null}, sprayed_on, source}`.
`created_at` and `request_id` are not exposed.

## Decisions I made where the spec is silent

1. Any known pesticide id is accepted regardless of the zone's crop (Non-goals).
2. `existing` in the 409 is the lowest-id record when several exist.
3. `limit` below 1 is 422 (the spec gives only the default and the maximum).
4. An unknown `pesticide_id` is 422 (a bad request value), not 404.
5. `request_id` is looked up before the duplicate check, as the spec orders it, and a retry returns
   the stored record unchanged even if its pesticide or date differ from the retry.
6. `spray_log` rows are read through `text()` SQL in a repository module, not ORM models: no ORM
   model exists in the repo and `schema.sql` is the single source of the table definition.

## Tests

DB-backed through the existing `client`, `make_user`, `make_field`, `make_zone` fixtures; pesticide ids
come from `catalog_service.list_pesticides`, not hard-coded numbers.

- Auth and ownership for all three routes, including a foreign zone with an invalid body (404 wins).
- POST: shape and 201; default date; tomorrow is 422 and today is accepted; unknown pesticide 422;
  bad `source`, missing or non-UUID `request_id` 422.
- Idempotency: replay returns 200 with the same id and stores one row; replay ignores
  `allow_duplicate` false; `request_id` of another zone or another user is 422 with no leak; the lost
  race paths with the first `request_id` lookup forced empty: insert returns nothing and the re-read
  answers 200 (`allow_duplicate` true), and the pre-409 re-check answers 200 (`allow_duplicate`
  false).
- Duplicates: 409 with `existing`; nothing stored by the 409; resend with `allow_duplicate` is 201;
  lowest-id `existing`; different date, pesticide or zone is not a duplicate.
- GET: order and tie-break, paging, `total`, bounds 422, other zones excluded, empty history, `moa`
  null and non-null.
- DELETE: 204 and empty body, gone from the list, second delete 404, record of another zone 404,
  foreign zone 404.
- `get_pesticide`: an oracle over every drug of `_drugs()` and an unknown id.

## Known limits

- A retry of an already cancelled save would create the record again, because cancel is a hard
  delete and frees the `request_id`. The client makes a new `request_id` per save action, so this
  needs a delayed duplicate request after a manual cancel.
- A stored `pesticide_id` that later disappears from the catalog would make the list fail to resolve
  it. The catalog never renumbers or removes `use_id`s (architecture document, catalog data notes),
  so no handling is added.

## Coordination (no work in this task)

- 혜빈님's zone summary needs the latest spray: `spray_service.list_sprays(db, zone_id, limit=1,
  offset=0)` already returns it. A batch function can be added when she needs one.
- BE-45 needs the whole history of a zone as pure records; it will add that function then.
