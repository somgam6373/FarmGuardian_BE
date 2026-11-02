# API changes for the frontend integration (2026-11-02)

- Purpose: a hand-off list of every API change made on branch `feat/frontend-integration-be`, to update the Notion 「API 명세서」 database from a session that can reach Notion. This session could not (no Notion tool, no browser).
- Compared against: the API contract before this work, i.e. `팜가디언_API_명세.md` as of commit `0c06ef8` (28 endpoints). Commits `8bd0fe0` … `5d2412b`.
- Source of truth: `docs/dev/팜가디언_API_명세.md` (already updated, Korean, with 【결정】 marks). If this file and the 명세 disagree, the 명세 wins; fix this file.
- All changes are additive except two behaviour changes (spray cancel, `GET /pests` list). No field was removed or renamed.

## How to use this in the Notion session

1. Open the Notion 「API 명세서」 database and read its columns first (this session never saw them). Map the columns below onto them.
2. Add 2 rows (new endpoints), edit the rows in 「Changed endpoints」, then fix the counts (28 → 30 endpoints, counting the unbuilt `GET /zones/{id}/weather`; 준혁 19 → 21).
3. Copy the shared types (「Types」) into whatever page or column holds `Pesticide`, `PestCard`, `Spray`, `Field`, `Zone`.
4. Mark each new decision as 【결정】 like the 명세 does, and tell the frontend that the response changes need their approval (아키텍처 §9, `openapi.json` contract).

## New endpoints (2)

| Method and path | Owner | Auth | Summary |
|---|---|---|---|
| `GET /zones/{zone_id}/judgments/preview` | 준혁 | `X-User-Id` | Judge every drug of one (zone, pest) without saving. Query `pest_id` (required), `apply_date` (optional). 200 `[PreviewItem]`. Errors: 401, 404 (not your zone, unknown pest, pest of another crop), 422 (`pest_id` missing → `loc ["query","pest_id"]`; `apply_date` after 2100-12-31). Same drug pool and order as `GET /pesticides` for that crop and pest (moa → item_name → brand). Stores nothing. One item's `result` equals the `POST /judgments` result for the same input. Pool sizes: 91 pairs, median 18, max 274 → response is gzip |
| `POST /zones/{zone_id}/sprays/{spray_id}/restore` | 준혁 | `X-User-Id` | Undo a cancelled spray. 200 `Spray`. 404 if the spray is not in that zone. Calling it on an active spray is a 200 no-op. A restored spray may duplicate another same-day same-drug record (allowed) |

## Changed endpoints

| Endpoint | Request change | Response change | Behaviour and errors |
|---|---|---|---|
| `POST /auth/signup` | body adds `field_address?: string` (stripped, 1–200 chars) | `field.address` | blank or 201+ chars → 422 `loc ["body","field_address"]`. A failed signup still leaves no user |
| `POST /fields` | body adds `address?: string` (stripped, 1–200 chars) | `Field.address` | blank or 201+ → 422 `loc ["body","address"]`. The address cannot be edited afterwards (no `PATCH /fields`) |
| `GET /fields` | – | `Field.address`; each `ZoneSummary.harvest_at` | fields created before this change have `address: null`. `ZoneSummary.last_spray` keeps its old 4-key shape (`pesticide` stays `Pesticide`) and skips cancelled sprays |
| `GET /zones/{id}` | – | `harvest_at` | – |
| `POST /fields/{id}/zones` | – (`ZoneSpec` unchanged; no `harvest_at` here) | each `Zone.harvest_at` (always null on creation) | – |
| `PATCH /zones/{id}` | body adds `harvest_at?: date\|null` | `harvest_at` | `harvest_at` must be on or after `planted_at` when both are set, else 422 (`loc ["body","harvest_at"]` if sent, else `["body","planted_at"]` when a new `planted_at` is later than the stored `harvest_at`). A past date is allowed. A crop change sets `harvest_at` to null unless the same request sends one. A `planted_at`-only change keeps it. `history_confirmed` is not touched by `harvest_at` |
| `GET /pesticides` | – | items become `PesticideDetail + at_planting_only` | – |
| `GET /pests`, `GET /pests/candidates` | – | `PestCard` adds `months`, `pesticide_count`, `is_virus`, `carries` | `GET /pests` also lists virus pests (no registered drug, `pesticide_count: 0`): 감자 25, 배추 43 → 45, 토마토 23 → 27 |
| `POST /ocr/pesticide-labels` | – | `candidates[].pesticide` becomes `PesticideDetail`; adds `candidates[].matched` | `matched` ⊆ `["brand","product","company"]`, always in that order. brand/product match at similarity ≥ 0.9; company at ≥ 0.9 or when one name contains the other. An unread field never matches. `score` and ranking are unchanged |
| `POST /zones/{id}/judgments` | – | adds `pesticide` (`PesticideDetail + at_planting_only`); `alternatives[]` become `PesticideDetail`; ① `facts.dilution`; ② `facts.harvest_at`, `facts.margin_days` | see 「Judgment ② rule」 below. Both new ② keys appear only when the zone has `harvest_at` and the drug's pre-harvest days are known |
| `POST /zones/{id}/sprays` | body adds `pest_id?: int\|null` | `Spray` adds `pest`, `cancelled`; `pesticide` becomes `PesticideDetail` | unknown `pest_id` → 422 `loc ["body","pest_id"]` (existence only; crop match is not checked). The same `request_id` replays the original row even if it was cancelled since (then `cancelled: true`) |
| `GET /zones/{id}/sprays` | – | items are the new `Spray` | **cancelled sprays are returned too** with `cancelled: true`, and `total` counts them. Order unchanged. The frontend counts active rows itself |
| `DELETE /zones/{id}/sprays/{sid}` | – | still 204, no body | **now a soft cancel**: the row stays and only `cancelled_at` is set. Cancelling twice is 204. 404 if not in that zone |

Not changed: `POST /auth/login`, `GET /me`, `POST /me/onboarding`, `DELETE /me`, `GET /crops`, `GET /crops/{id}/symptom-parts`, `DELETE /fields/{id}`, `POST /fields/{id}/split-preview`, `GET /addresses/search`, `GET /parcels`, the three `/inventory` endpoints, `GET /health`. `GET /zones/{id}/weather` is still not built (the frontend keeps a mock).

## Common change

Responses of 1,000 bytes or more are gzip-compressed for requests with `Accept-Encoding: gzip`. Not counted as an endpoint change.

## Types

```
PesticideDetail  {id, name, item_name, moa: Moa|null,
                  company: string|null, form: string|null, ingredients: [string],
                  kind: "insecticide"|"fungicide"|"both"|null}
                 form = last word of item_name (e.g. 액상수화제); kind from the usage column
                 (살충/살균/균충); company = company of the drug's first registration row;
                 ingredients = active ingredient names
PesticideOut     PesticideDetail + {at_planting_only: bool}        (GET /pesticides, JudgeResponse.pesticide)
PreviewItem      {pesticide: PesticideDetail, at_planting_only: bool, result: JudgeResult}
JudgeResponse    {judgment_id, apply_date, pesticide: PesticideOut, result, alternatives: [PesticideDetail],
                  show_extension_office}
Spray            {id, pesticide: PesticideDetail, pest: {id, name}|null, sprayed_on, source, cancelled: bool}
PestCard         old keys + {months: [int], pesticide_count: int, is_virus: bool, carries: [{id, name}]}
                 months = months of the chosen season row ([] when none; 80 of 129 pests have none)
                 pesticide_count = drugs registered for that crop × pest (0 if none)
                 carries = viruses this pest vectors, sorted by name
Field            old keys + {address: string|null}
Zone, ZoneSummary  old keys + {harvest_at: date|null}
LabelCandidate   {pesticide: PesticideDetail, score, matched: ["brand"|"product"|"company"]}
```

`ZoneSummary.last_spray` is the exception: it keeps `{id, pesticide: {id, name, item_name, moa}, sprayed_on, source}`.

## Judgment ② rule (the one behaviour change that affects verdicts)

Before: ② never returned `BLOCKED`. Now, only when the zone has `harvest_at` and the strictest `phi` is readable:

```
margin_days = (harvest_at − apply_date).days − phi
margin < 0        → BLOCKED   (harvest_at before today: "수확 예정일(N월 N일)이 지났습니다";
                               otherwise "수확 예정일(…)까지 N일 남아 수확 N일 전까지 사용하는 기준을 지킬 수 없습니다")
0 ≤ margin ≤ 2    → CAUTION   ("수확 예정일(…)까지 여유가 N일입니다 (수확 N일 전까지 사용)")
otherwise         → OK        (unchanged message)
```

Without `harvest_at`, or for NO_LIMIT, AT_PLANTING and unreadable-phi drugs, ② is exactly as before and the two new keys are absent. Reason: a harvest inside the pre-harvest interval is a shipping ban (approved 2026-11-02, design C1). `harvest_at` is also used by `GET .../judgments/preview`.

Other judgment `facts` change: ① `registration.facts.dilution` = the raw dilution text of the first considered row (string or null), only when ① is `OK`. No water volume is computed (dilution calculation is P1).

## Behaviour that cancelled sprays no longer affect

A cancelled spray is excluded from: judgment ③ count and ④ consecutive-use window, the rotation summary (`GET /zones/{id}` → `rotation`), the same-zone/drug/day duplicate check (so no `DUPLICATE_SPRAY` against it), and `ZoneSummary.last_spray`. It is only visible through `GET /zones/{id}/sprays`.

## Database changes (teammates run these by hand; there is no Alembic)

```sql
ALTER TABLE spray_log ADD COLUMN pest_id int, ADD COLUMN cancelled_at timestamptz;
ALTER TABLE zone  ADD COLUMN harvest_at date;
ALTER TABLE field ADD COLUMN address text;
```

`schema.sql` already has all three. Without them spray, zone, field and signup requests fail.

## Not done, so do not document as available

- `GET /zones/{id}/weather` (frontend keeps a mock), neighbour statistics (mock), zone deletion or re-split, dilution calculation, content (함량) data, peak-month data.
- `api_playground.html` does not list the two new endpoints yet.

## Where to check

| Item | File |
|---|---|
| Full contract (Korean) | `docs/dev/팜가디언_API_명세.md` §2, §3, §5, §6, §7, §8 |
| Judgment rules and test cases T15–T19 | `docs/dev/팜가디언_판정_규칙.md` §4 ② |
| Why each change exists (B1–B11, C1–C5) | `docs/dev/2026-11-02-frontend-integration-design.md` |
| Real response models | `app/*/presentation/schemas.py` |
