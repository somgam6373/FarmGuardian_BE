# Zone detail and last judgment (design)

- Date: 2026-10-30
- Owner: Hyebin (farm context), issue #6 (rest) and the `last_judgment` follow-up of #4
- Status: approved in chat (2026-10-30)
- Basis: `팜가디언_API_명세.md` §2 (`Zone`, `ZoneSummary`, `JudgmentBrief`, `Rotation`, `Moa`), §5
  `GET /zones/{id}`, §9 홈; `2026-10-30-judgment-reader-design.md` (Junhyeok, PR #24: the functions to call).
  Stacks on `feat/hb-zone-detail` (zone update, not merged yet).

## Goals

1. `GET /fields`: each `ZoneSummary.last_judgment` = `reader.last_judgments(db, zone_ids)` result for that
   zone (one call for all zones of the user), `null` when the zone has none.
2. `GET /zones/{zone_id}` → 200 `Zone` + `{rotation: Rotation, recent_judgments: [JudgmentBrief]}`:
   `rotation = reader.rotation(db, zone_id, zone.planted_at)`, `recent_judgments =
   reader.recent_judgments(db, zone_id)` (newest 5). 404 for someone else's / unknown zone
   (`get_owned_zone`), 401 without header.
3. Typed response models for `JudgmentBrief` and `Rotation` so the OpenAPI docs show their shape
   (my call; Junhyeok's design left them untyped because the farm fields were `dict`).
   - `JudgmentBrief {judgment_id: int, created_at: datetime, pesticide: {id, name, item_name},
     pest: {id, name} | null, verdict: "OK"|"CAUTION"|"BLOCKED"|"NEEDS_CHECK"}`
   - `Rotation {window_start: date | null, total: int, items: [{moa: Moa | null, count: int}]}`,
     `Moa` = catalog `MoaOut`.

## Non-goals

- Changes in `app/judgment/` (functions are used as they are).

## Tests

- `GET /fields`: a zone with two judgments → `last_judgment` is the newer one (keys as `JudgmentBrief`);
  a zone without → `null`.
- `GET /zones/{id}`: keys = `Zone` keys + `rotation`, `recent_judgments`; with sprays the rotation
  counts them; 6 judgments → 5 newest first; `created_at` string ends with `+09:00`; 404 / 401.
- Judgments and sprays inserted with SQL using real catalog ids (`catalog_service.list_pesticides(1)`).
