# Frontend prototype ↔ API integration (design)

- Date: 2026-11-02
- Owner: Junhyeok (backend lead; `catalog`, `judgment`, `spraying`, `identity` contexts) + frontend wiring
- Status: **draft, awaiting approval** (one rule change below needs an explicit yes: C1)
- Basis: a screen-by-screen read of `frontend/src` (10 screens, `AppState`, `mock.ts`, `lib/verdict.ts`) against the
  27 implemented endpoints (`GET /zones/{id}/weather` is in the spec but not built, which is why weather stays mock);
  `팜가디언_API_명세.md`, `팜가디언_판정_규칙.md`, `팜가디언_아키텍처.md`; the static catalog in
  `app/catalog/data`.
- Rule applied: when UI and API disagree, **keep the prototype UI** and extend the backend that is ours. Anything
  under `app/farm` (Hyebin's) is **not edited by us**; it is listed in `팜가디언_혜빈님_요청_프론트연동.md`.
  What the documents leave open, the team decides (`【결정】`).

## Intent

The frontend is a hard-coded prototype: no `fetch`, every screen reads `data/mock.ts` and evaluates verdicts on the
client (`lib/verdict.ts`). The backend API is done. This design decides, per gap, how the prototype is wired to the
real API, which backend pieces we add, and which prototype pieces we drop. Success: every screen runs on the real
API except the two parts kept as mock (weather card, neighbour statistics).

## Decisions (made with the user, 2026-11-02)

| # | Topic | Decision |
|---|---|---|
| 1 | Default rule | Keep prototype UI; extend our backend; Hyebin's area is documented separately |
| 2 | Login | Kakao button → ID/password form (+ signup). Guest browsing removed |
| 3 | Verdict lists | New read-only batch judgment API (B1) |
| 4 | Drug info | Add company, ingredients, kind, form (B2) and dilution (B3). **Content (함량 25%) dropped from the UI** |
| 5 | Harvest date | Zone gets `harvest_at` (Hyebin) and ② uses it (C1, needs approval) |
| 6 | Spray records | Store `pest_id`; soft cancel + restore (B4) |
| 7 | Neighbour statistics | Stays mock (like weather) |
| 8 | Crops | Only the 3 in the catalog (`GET /crops`) |
| 9 | Pest card | Add `months`, `pesticide_count`, virus flag; **peak emphasis dropped** (B5) |
| 10 | 「심을 때」 status | Derived in the frontend (planted_at empty, or drug is `at_planting_only`) |
| 11 | OCR match reason | Backend returns which fields matched (B6) |
| 12 | Past-record drug picker | Crop-registered drugs only (two `GET /pesticides` calls) |

## Goals

1. Each screen below works on the real API.
2. Backend additions are additive: no existing field changes meaning, `app/farm` files are untouched.
3. The server verdict replaces the client's `evaluate()` everywhere.

## Non-goals

- Real weather and neighbour statistics (kept as mock, labelled as sample data in the UI).
- Kakao OAuth, guest mode, a demo account, content (함량) data, peak-month data, crops other than the 3.
- Anything in `app/farm` (see the Hyebin document).

## Conflicts with existing documents

**C1. ② timing and the harvest date (needs approval).** `팜가디언_판정_규칙.md` §1/§4 ② decided: the harvest date is
**not** an input, ② shows `harvest_from` and **never returns `BLOCKED`**. Decision 5 reverses that. Proposed rule,
mirroring the prototype's thresholds: when `zone.harvest_at` is set and the strictest `phi` is known,
`margin_days = (harvest_at − today).days − phi`; `margin < 0` → `BLOCKED`, `0 ≤ margin ≤ 2` → `CAUTION`, otherwise `OK`;
`facts` gain `harvest_at` and `margin_days`. With no `harvest_at`, ② behaves as today. Touches: judge_rules §1 table
and §4 ② and §9 cases, `rules.py`, `팜가디언_PRD_수정_제안.md`, and `ZoneContext` in `app/farm/application/zone_reader.py`
(Hyebin). **Fallback if not approved:** store `harvest_at` only for the 「D-N」 display, leave ② unchanged, hide 「여유 N일」.

**C2. 「취소 = 삭제」.** The API spec says cancelling a record deletes it. B4 changes that to a soft cancel (row kept,
restorable). The Settings screen's note 「취소한 기록도 삭제 없이 보존」 becomes true.

**C3. Judgments are saved.** `POST /zones/{id}/judgments` stores every call. The Verdict screen keeps using it (one call per
screen view); lists use B1, which stores nothing.

## Backend changes (ours)

### B1. Batch judgment preview — `GET /zones/{zone_id}/judgments/preview` (judgment)

- Query: `pest_id` (**required** 【결정】, so the pool stays small), `apply_date` (optional, same rule as the POST).
- Response 200: `[{pesticide: PesticideDetail, at_planting_only: bool, result: JudgeResult}]`, ordered as `GET /pesticides`
  (moa → item → brand). Same pool as `catalog_service.list_pesticides(crop_id, pest_id)`.
- Saves nothing. Reads the zone context and spray history **once**, then runs `judge()` per drug in memory.
- Errors: 401, 404 (zone not owned / unknown pest or pest of another crop), 422 (missing `pest_id`; `apply_date` > 2100-12-31).
- Used by: MapHome sheet (top 3), DrugList (groups and tally), Dashboard 「다음에 쓸 약」.
- Code: a `preview()` next to `run_judgment()` in `judgment/application/service.py`, sharing `assess()`'s `judged()`.

### B2. `PesticideDetail` (catalog)

`PesticideDetail(PesticideBase)` adds `company: str | None`, `form: str | None`, `ingredients: list[str]`,
`kind: "insecticide" | "fungicide" | "both" | null`. `PesticideOut` extends it (adds `at_planting_only`).
Used in: `GET /pesticides`, judgment `alternatives`, preview, OCR candidates, `SprayOut.pesticide`.
**`PesticideBase` stays as is**, because `LastSpray` in `app/farm/presentation/schemas.py` uses it, so `GET /fields` is unchanged.

Derivation (checked against the data: 1363 drugs):

| Field | Source |
|---|---|
| `form` | last space-separated token of `item_name` (all 1363 have a space; 25 forms, e.g. 액상수화제) |
| `ingredients` | `use_ingredient` by `seq` → `ingredient.name` (rows of one drug never disagree) |
| `kind` | `pesticide_use.usage`: 살충→insecticide, 살균→fungicide, 균충→both (never differs within a drug) |
| `company` | company of the drug's first row (lowest `use_id`) 【결정】; 83 drugs have 2+ companies |

### B3. Dilution — `facts.dilution` on the ① `registration` check

String, the raw `dilut_raw` of the first considered row (the row already used for `evidence`), or null. The UI shows it
as 「희석 2000배」; water per area (「물 N L」) stays a client calculation. Needs the ① facts table in judge_rules §4 and 명세 §7 updated.

### B4. Spray records: `pest_id` and soft cancel (spraying)

- Schema (`schema.sql`, `spray_log`): `pest_id int NULL` (static pest id, no FK), `cancelled_at timestamptz NULL`.
- `POST /zones/{id}/sprays` body gains `pest_id?: int|null` (unknown id → 422 `loc ["body","pest_id"]`; existence check only 【결정】).
- `Spray` (POST/GET response) gains `pest: {id, name} | null` and `cancelled: bool`; `pesticide` becomes `PesticideDetail`.
- `GET /zones/{id}/sprays` returns cancelled rows too (`cancelled: true`); `total` counts them. Order unchanged.
- `DELETE /zones/{id}/sprays/{sid}` → sets `cancelled_at`, still 204 (already cancelled → 204 too 【결정】); 404 as before.
- New `POST /zones/{id}/sprays/{sid}/restore` → 200 `Spray`; 404 if not found. Restoring may create a same-day same-drug pair; allowed 【결정】.
- **Cancelled rows are excluded from everything that decides**: `spray_service.history()` (judgment input and, through
  `judgment/application/reader.py`, the rotation summary), `find_duplicate`, and `list_sprays()` by default. The router for
  `GET /sprays` passes `include_cancelled=True`. This keeps `zone_service._last_spray` (Hyebin's file) correct **without editing it**.
- `request_id` replay still returns the original row even if it was cancelled since (shows `cancelled: true`) 【결정】.
- The dev and test databases need the two columns (`ALTER TABLE`); teammates run it too. Needs the user's go-ahead.

### B5. Pest card (catalog)

`PestCard` / `PestCardOut` gain: `months: [int]` (from the chosen season row, `[]` when none; 49 of 129 pests have one),
`pesticide_count: int` (drugs registered for that crop × pest; 0 if none), `is_virus: bool` (id in `virus_vector.virus_pest_id`),
`carries: [{id, name}]` (viruses this pest vectors, from `virus_vector.vector_pest_id`). `kind`, `occurrence` and the rest are
unchanged. No `peak`. `pesticide_count` should come from a cached per-(crop, pest) count, not a scan per card 【builder's call】.

### B6. OCR match reason (catalog)

Each candidate gains `matched: ["brand" | "product" | "company", …]`. A field counts when the read value and the drug's
`name` / `item_name` / `company` have normalized similarity ≥ 0.9 【결정, tune with real photos like `CUTOFF`】. `score` and the
ranking do not change. If a drug has several companies, any one may match.

### B7. ② harvest margin — only if C1 is approved (judgment)

As written in C1. Depends on Hyebin adding `harvest_at`.

## Frontend changes (by screen)

| Screen | Change |
|---|---|
| (all) | New `api/` layer: base URL (Vite env/proxy), `X-User-Id` from storage, error mapper for `{error:{code,…}}`; ids become numbers; remove `TODAY` (use KST today); server state replaces `mock.ts` in `AppState` (selected zone/pest stay local) |
| Login `/` | Replace Kakao and 「둘러보기」 with login + signup. Signup = address search → parcel pick (`/addresses/search`, `/parcels`) → field name → `POST /auth/signup` |
| MapHome | Farm card/zones from `GET /fields`; `FieldMap` draws `geometry` (EPSG:5179, flip y); top-3 drugs from B1; sheet shows 심은 날 only (D-N needs `harvest_at`); **weather stays mock** |
| ScanSheet | Upload to `POST /ocr/pesticide-labels`; lines = `read.text` split by newline; candidate text from `matched` (table below); 「예시 사진」 stays a labelled canned result 【결정】 |
| PestSelect | Parts from `symptom-parts`; list from `candidates` or `pests` (both filters combined client-side); bar from `months` (no peak); count from `pesticide_count`; virus tag/notes from `is_virus`, `vectors`, `carries` |
| DrugList | B1 groups and tally; 「심을 때」 derived; card fields from `PesticideDetail` |
| Verdict | `POST /judgments`; checks mapped by key; chips rebuilt from `facts`; alternatives from the response; record button sends `request_id`, `pest_id`, `source:"app"`; 409 dialog (기존 기록 확인 / 별도 살포로 저장 / 돌아가기) |
| History | Per-zone `GET /sprays` merged for 「전체」; pest column; soft cancel/restore; add form: pest from `GET /pests`, drug from two `GET /pesticides` calls |
| Fields | `PATCH /zones/{id}` with an explicit save (not per keystroke); farm/zone creation and deletion follow the Hyebin document |
| Dashboard | Totals from `GET /zones/{id}` `rotation`; drug names per group from sprays; 「다음에 쓸 약」 from B1; **neighbour card stays mock** |
| Settings | Account copy for ID/password; 로그아웃 clears the stored id; add 회원 탈퇴 (`DELETE /me`) with a confirm screen; fix the 카카오 line in the privacy list |
| **New: 누락 없음 confirmation** | See below |

**누락 없음 (required).** Server rules ③④ return 확인 필요 until the zone's 「누락 없음」 is confirmed (`history_confirmed`, reset
whenever `planted_at` changes). The prototype has no such step, so without one **every drug would show 확인 필요**. Add a banner
per zone on History (and in the zone editor) that calls `PATCH {history_confirmed:true}`. Placement is my call 【결정】. The backend
does not require `POST /me/onboarding` for anything else; the prototype does not gate tabs on it 【결정】.

Status mapping: `OK→ok`, `CAUTION→caution`, `BLOCKED→no`, `NEEDS_CHECK→unknown`; `preplant` is derived (decision 10).
Check keys: `reg→registration`, `timing→timing`, `count→count`, `group→moa`.

OCR copy: all three of brand/product/company → 「이름 · 성분 · 회사 일치」; `product` only → 「성분만 같아요」; otherwise → 「이름이 비슷해요」 【결정】.

## Behaviour that changes when the server judges

| Prototype (client) | Server (judge_rules) | UI effect |
|---|---|---|
| ③ last allowed use → `caution` | `OK` with a message | badge stays 가능; text says 마지막 횟수 |
| ③ counted per ingredient | counted per `item_name` | counts can differ |
| ④ twice in a row → `no` | `CAUTION` only, rule per MOA (§4 ④) | no 불가 from ④ |
| ④ over this season | window ignores season | — |
| not registered → ②③④ `skip` | ① `BLOCKED`; ②③ `NEEDS_CHECK`; ④ still computed | 「해당 없음」 becomes 「자료 없음」 for ②③ |
| no 누락 없음 concept | ③④ `NEEDS_CHECK` until confirmed | needs the new confirmation UI |
| `harvestAt` margin → `no`/`caution` | ② never blocks | only with C1 |

## Docs to update when built

`팜가디언_API_명세.md` (28 → 30 endpoints counting the unbuilt weather one, spray section, `Pesticide`/`PestCard` types, §7 facts, 취소 wording),
`팜가디언_판정_규칙.md` (③ facts, ① `dilution`; ② if C1), `팜가디언_아키텍처.md` (§5 `spray_log`, §7 table),
`schema.sql`, `api_playground.html` if it lists these APIs, Notion 「API 명세서」, the BE backlog (one row per B-item).

## Open items only the team can answer

1. **C1**: approve the ② rule change (recommended: yes, thresholds as the prototype), or take the fallback.
2. Go-ahead to run the `ALTER TABLE spray_log` in the dev and test databases (B4).
3. Backlog ids and sprint for B1–B6.
4. Placement of the 누락 없음 banner (my call: History + zone editor).

## Left to the builder

How the Verdict screen learns `at_planting_only` for a drug reached through OCR (suggestion: add the flag to `JudgeResponse`);
the cached per-pest drug count (B5); the exact similarity function and threshold for B6.
