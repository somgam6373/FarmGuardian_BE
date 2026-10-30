# Judgment read side for zone screens (design)

- Date: 2026-10-30
- Owner: Junhyeok (judgment context)
- Status: approved in chat 2026-10-30 (option A: functions only, Hyebin wires them)
- Frame: `팜가디언_API_명세.md` §1 (datetime rule), §2 (`JudgmentBrief`, `Rotation`, `ZoneSummary`,
  `Zone`), §5 `GET /fields`, `GET /zones/{id}`; `schema.sql` `judgment`.

## Intent

Judgments are saved by `POST /zones/{id}/judgments` but nothing reads them back. Two screens need them:
`GET /fields` (each `ZoneSummary.last_judgment`, today a constant `null` in `farm/application/zone_service.py`)
and `GET /zones/{id}` (`rotation` and `recent_judgments`). Both endpoints belong to Hyebin (spec §0), so
this adds the functions she calls; it adds no route.

## Goals

New module `app/judgment/application/reader.py`, three functions, all returning plain dicts shaped like
the spec so they drop into her `dict` fields:

1. `last_judgments(db, zone_ids: list[int]) -> dict[int, dict]`: the newest `JudgmentBrief` per zone, one
   SQL statement for all zones. Zones without a judgment are absent from the result.
2. `recent_judgments(db, zone_id: int, limit: int = 5) -> list[dict]`: newest first (`created_at DESC`,
   then `id DESC`).
3. `rotation(db, zone_id: int, planted_at: date | None) -> dict`: the spec's `Rotation`, from the zone's
   spray history through the existing `rotation_summary`.

`JudgmentBrief` (spec §2, marked 【결정】, not yet agreed with the frontend):
`{judgment_id, created_at, pesticide: {id, name, item_name}, pest: {id, name} | null, verdict}`.
`created_at` follows spec §1: KST, seconds, `YYYY-MM-DDTHH:MM:SS+09:00` on the wire. The function returns
an aware `datetime` in `KST` with `microsecond=0`; FastAPI's encoder writes the offset.

## Non-goals

- Any route, any change to `app/farm/`, `schema.sql` or the spec. Hyebin makes the calls (below).
- Pydantic response models for the two shapes: her fields are `dict`, so the OpenAPI docs stay untyped
  there for now.
- Ownership checks: the route already answered 404 for someone else's zone (spec §1).

## Decisions

1. **Names come from the static catalog**: `catalog_service.get_pesticide` and `get_pest_card(...).name`.
2. **A stored judgment whose pesticide or pest is no longer in the catalog is skipped**, not an error. Ids are
   frozen by policy and `assess` validates them at write time, so this should not happen, but a 500 here
   would take down the home screen. `recent_judgments` drops the row (it may then return fewer than
   `limit`); `last_judgments` leaves that zone out instead of falling back to an older row.
3. **`rotation` takes `planted_at` as an argument** instead of reading the zone: her `GET /zones/{id}` has the
   row already, and it avoids a second query and a second dependency on `zone_reader`.
4. **The spray-history to `SprayRecord` conversion moves out of `assess`** into a public
   `service.spray_records(history)` that both `assess` and `rotation` use (pure refactor, tests unchanged).
5. Verdict stays the stored string (`OK`, `CAUTION`, `BLOCKED`, `NEEDS_CHECK`, the spec's `Verdict`).

## Coordination: what Hyebin calls

```python
from app.judgment.application import reader

# zone_service.summaries, once per call for the whole field list
last = reader.last_judgments(db, [row.id for row in rows])      # before the loop
"last_judgment": last.get(row.id),                              # replaces the constant None

# GET /zones/{id}
{**zone, "rotation": reader.rotation(db, zone_id, planted_at),
 "recent_judgments": reader.recent_judgments(db, zone_id)}
```

Import direction: `reader` imports `judgment.application.service`, which imports
`farm.application.zone_reader` (not `zone_service`), so `zone_service` importing `reader` makes no cycle.
Her existing tests that assert `last_judgment is None` stay true for zones without a judgment.

## Tests

DB-backed, flat file `tests/test_judgment_reader.py`, judgments inserted with SQL (explicit `created_at`
where order matters; inside one test transaction `now()` is constant, so the `id` tie-break is exercised).
Order and limit, other zones never leak, exact key sets, null pest, the KST wire string through
`jsonable_encoder`, a stale catalog id, one SQL statement for several zones, and rotation with no
sprays, a `planted_at` window, and unknown-moa sprays last.
