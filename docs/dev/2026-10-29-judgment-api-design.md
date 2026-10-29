# Judgment API (BE-45) Design

Date: 2026-10-29. Frame: `docs/dev/팜가디언_API_명세.md` §7 (never edited; this design conforms to it).
Rules: `팜가디언_판정_규칙.md` (§3, §5, §7), `2026-10-29-judge-registration-timing-design.md` (row mapping).

## Goal

`POST /zones/{id}/judgments`: judge one pesticide (optionally against one pest) for a zone with the
finished pure domain (`judge`, `pick_alternatives`), build the alternatives, save the judgment, and
answer a `JudgeResponse`.

The domain is done and merged (checks ①–④, `judge`, `rotation_summary`, `pick_alternatives`). This task
is the glue: turn static catalog rows, the zone and its spray history into a `JudgeInput`, run it,
add what only the service adds, and store it.

## Non-goals

- `rotation` and `recent_judgments` of `GET /zones/{id}` and `last_judgment` of the zone summary:
  `farm` (혜빈님) asks for them later; `judgment.application.service` will get those functions then.
- Reading a stored judgment back (the spec has no endpoint for it).
- Weather, auth, anything outside §7.

## Layout

```
app/judgment/
  domain/                        unchanged
  application/service.py         assess() — no DB; run_judgment() — reads, assesses, saves
  infrastructure/repository.py   INSERT into judgment (first and only SQL of this context)
  presentation/router.py, schemas.py
```

Additions in other contexts, each the smallest thing the judgment needs:

- `catalog`: `UseRow` entity; `get_registrations(pesticide_id, crop_id) -> list[UseRow]` (every
  `pesticide_use` row of that drug for the crop joined to its `safe_use_std` row, ordered by `use_id`);
  `data_asof() -> date` (the `base_date` of the static data, 2026-10-05).
- `spraying`: `spray_service.history(db, zone_id) -> list[SprayView]` — all records of the zone, newest
  first, pesticide resolved (the list endpoint pages, the judgment needs everything).
- `farm`: `application/zone_reader.py` with `get_zone_context(db, zone_id) -> ZoneContext(crop_id,
  planted_at, history_confirmed)`. See Coordination.
- `app/main.py` registers the router. `팜가디언_아키텍처.md` §4 line "judgment에는 infrastructure가
  없다" gets one clause: only the repository that stores judgments.

## Data flow

1. Router: `get_owned_zone` (404), body `JudgmentIn {pesticide_id, pest_id?, apply_date?}`,
   `today = today_kst()`.
2. `run_judgment` reads the zone context, the spray history and calls `assess`.
3. `assess` (pure apart from the in-memory catalog; raises only `AppError`):
   - chosen pesticide `catalog.get_pesticide` (404), pest check through
     `catalog.list_pesticides(crop_id, pest_id)`, which already answers 404 for an unknown pest or a
     pest of another crop and returns the candidate pool at the same time.
   - `JudgeInput(today=apply_date, planted_at, history_confirmed, pest_id, pesticide_id, item_name,
     moa, registrations, history, psis_asof)` with `Registration`s from `UseRow` (mapping below) and
     `SprayRecord`s from the history (`item_name` and `moa` of each record's pesticide).
   - `judge(inp)`, then the two things the service adds (judgment rules §5, §7, spec §7):
     notices, alternatives, `show_extension_office`.
4. `run_judgment` stores the row and commits; the router answers 201.

### Mapping of a `UseRow` to `Registration`

As fixed in the BE-38·39 design: `pest_id`, `pest_name`; `phi_days`, `max_uses` from
`safe_use_std.phi_days` / `max_count`; `use_suittime_raw`, `use_num_raw`, `dilut_raw`, `use_method`
from `use_time`, `use_count`, `dilution`, `method`; `usage_type` from `parse_status` (`ok` → NORMAL,
`stage` → AT_PLANTING, `no_std` → NO_LIMIT, `failed` → CHECK); `data_asof` from `base_date`. The
`usage_type` mapping lives in the judgment service (it is a judgment concept); the catalog only hands
over `parse_status`.

### Service additions

- **Notices:** if no pest was given and the verdict is `BLOCKED`, append 「병해충을 지정하면 대안을 볼
  수 있습니다」 (the domain already adds its own one-line notice).
- **Alternatives:** only when a pest was given. Pool = the drugs registered for the zone's crop × that
  pest, minus the chosen drug. Each candidate is judged with the same zone, history, `today` and pest
  (its own registrations, item name, moa), then `pick_alternatives(chosen_result, results)`. Order:
  `moa.label_kr`, `item_name`, `name`. No server cap.
- **`show_extension_office`:** a pest was given, the verdict is `BLOCKED` or `CAUTION`, and there are
  no alternatives.

### Persistence

`judgment(zone_id, pest_id, pesticide_id, apply_date, verdict, result jsonb)` with `result` =
`JudgeResult` as JSON (the evidence text and `data_asof` are the reproducible snapshot). `created_at`
is the column default. One row per successful call; a 404 or 422 stores nothing.

## Behavior of the endpoint

- Body: `{pesticide_id: int, pest_id?: int, apply_date?: date}`; `apply_date` default today (KST).
  `apply_date` is only the judgment's `today` (harvest date and wording); the zone's whole spray
  history is used regardless (spec).
- 201 `JudgeResponse {judgment_id, apply_date, result: JudgeResult, alternatives: [Alternative],
  show_extension_office}`; `Alternative` has the shape of `Pesticide`.
- 401 without a valid `X-User-Id`; 404 for a foreign or unknown zone (it wins over body validation),
  for an unknown pesticide, and for an unknown pest or a pest of another crop.
- 422 for a malformed body and for an `apply_date` after 2100-12-31 (`loc` `["body","apply_date"]`).
  The domain computes `today + phi_days`, which overflows near year 9999 and would otherwise be a
  500.
- A pesticide that is not registered for the zone's crop or pest is not an error: ① gives
  `BLOCKED` (spec).
- The judgment never writes spray records.

## Decisions I made where the spec is silent

1. `apply_date` upper bound 2100-12-31 (422). No lower bound; past dates only change the wording.
2. Validation order: zone (404) → body shape (422) → `apply_date` range (422) → pesticide (404) →
   pest (404).
3. `result` stores the `JudgeResult` only. Alternatives and `show_extension_office` are recomputable
   from the same inputs and nothing reads them back.
4. `assess` is a separate, DB-free function so the real data can be swept in a test without a
   database (see Tests).
5. The judgment context gets a repository (`infrastructure/`) for its own table, the same pattern as
   `spraying`.
6. A history record whose pesticide is no longer in the catalog is not handled (catalog ids never
   disappear; same limit as the spray list).

## Tests

- **Mapping oracle (no DB):** for sampled and for all real selections, a test-side loop builds the
  `Registration`s straight from the raw JSON and compares `assess(...).result` with `judge()` of that
  independent input.
- **Alternatives invariants:** all alternatives re-judge to `OK`, none has the chosen drug's moa
  label, none is the chosen drug, order is `(label_kr, item_name, name)`, none without a pest.
- **Service rules:** the unspecified-pest `BLOCKED` notice, `show_extension_office` true only for a
  pest-specified `BLOCKED`/`CAUTION` with an empty pool, false for `OK`, `NEEDS_CHECK` and
  unspecified; an unregistered drug is `BLOCKED` with no exception.
- **Real-data sweep (no DB):** every (crop, pest, drug) selection and every (crop, drug) without a
  pest runs through `assess`; no exception, always 4 checks, invariants hold. If the full sweep is too
  slow for the suite, it keeps every selection and a sample of histories, and the runtime goes in the
  plan.
- **API (DB):** 401; foreign zone with an invalid body is 404; unknown pesticide, unknown pest, pest
  of another crop are 404 and store nothing; `apply_date` 2101-01-01 and a non-date are 422;
  201 shape with exactly the spec's keys; the row is stored (verdict, `apply_date`, `pest_id` null or
  set, `result` JSON); two calls store two rows; `apply_date` default is today KST; a stored spray is
  seen by ③ (`facts.used`), including with a past `apply_date`; no spray record is created.

## Known limits

- Every call stores a row (no de-duplication); the table grows with use.
- The whole history of the zone is read each time (tens of records in practice).
- The candidate pool is judged one by one in memory; its size is bounded by the catalog (the sweep
  measures the worst case, and BE-50 measures the endpoint).

## Coordination

- **Zone reader.** The judgment needs `crop_id`, `planted_at` and `history_confirmed` of the zone, and
  `farm` has no zone read yet (`zone_service` is 혜빈님's). I add the smallest possible reader in a
  new file `farm/application/zone_reader.py` (a different name from her `zone_service.py`, so the two
  never collide). It is in her folder, so the change needs her review per the architecture rule; she
  can fold it into `zone_service` later by moving one function.
- When she builds `GET /zones/{id}` and the zone summary she will need `rotation_summary`,
  `recent_judgments` and `last_judgment` from `judgment.application.service`; I add them when she
  names the signatures.
